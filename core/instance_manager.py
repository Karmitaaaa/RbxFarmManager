"""Gestor de instancias: lanzamiento en cola, monitor de estado y auto-reconexión.

Hilos:
  - launcher: procesa la cola de lanzamientos de uno en uno (así cada PID nuevo se asocia
    sin ambigüedad a su cuenta).
  - monitor: cada 2 s revisa procesos, ventanas, diálogos de error, logs del cliente e internet.
Ambos emiten señales Qt; la UI solo lee instantáneas.
"""
import logging
import queue
import threading
import time

import psutil
from PySide6.QtCore import QObject, Signal

from core import launcher, performance, roblox_api, window_layout
from core.models import (ACTIVE_STATES, LOGIN_COOKIE, ST_CLOSED, ST_DISCONNECTED, ST_ERROR, ST_FAILED,
                         ST_INGAME, ST_LAUNCHING, ST_OPEN, ST_STOPPED, ST_WAIT_NET, ST_WAIT_RECONNECT,
                         Account, GameProfile, Instance, LaunchTarget)
from core.reconnect import backoff_delay, classify_log_line, internet_ok
from storage.config import Config
from utils import winapi
from utils.i18n import t

log = logging.getLogger("instancias")

MONITOR_INTERVAL = 2.0
NET_CHECK_EVERY = 10.0


class InstanceManager(QObject):
    changed = Signal()
    notify = Signal(str, str)          # nivel, mensaje
    joined = Signal(str)               # id de instancia que entró en juego

    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.mutex = launcher.MultiInstanceMutex()
        self._instances: dict[str, Instance] = {}
        self._procs: dict[int, psutil.Process] = {}
        self._lock = threading.RLock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self.online = True
        self._last_net_check = 0.0
        self._arrange_lock = threading.Lock()
        self._arrange_pending = False
        self._threads = [
            threading.Thread(target=self._launch_loop, name="launcher", daemon=True),
            threading.Thread(target=self._monitor_loop, name="monitor", daemon=True),
        ]

    def start(self) -> None:
        if self.cfg.get("launch.multi_instance"):
            self._prepare_multi_instance()
        for t in self._threads:
            t.start()

    def shutdown(self) -> None:
        self._stop.set()
        self.mutex.release()

    # ------------------------------------------------------------------ API pública
    def snapshot(self) -> list[Instance]:
        with self._lock:
            return list(self._instances.values())

    def get(self, inst_id: str) -> Instance | None:
        with self._lock:
            return self._instances.get(inst_id)

    def launch(self, accounts: list[Account], target: LaunchTarget, profile: GameProfile | None = None) -> None:
        with self._lock:
            for acc in accounts:
                running = [i for i in self._instances.values()
                           if i.account.id == acc.id and i.status not in (ST_STOPPED, ST_FAILED, ST_CLOSED)]
                if running:
                    self._emit("warning", t("{0}: ya tiene una instancia activa, se omite", acc.alias))
                    continue
                inst = Instance(account=acc, target=target,
                                anti_afk=profile.anti_afk if profile else acc.anti_afk,
                                auto_reconnect=profile.auto_reconnect if profile else True)
                if profile:
                    inst.profile_id, inst.profile_name = profile.id, profile.name
                inst.detail = t("En cola")
                self._instances[inst.id] = inst
                self._queue.put(inst.id)
        self.changed.emit()

    def close(self, inst_id: str) -> None:
        inst = self.get(inst_id)
        if not inst:
            return
        inst.user_closed = True
        self._kill(inst)
        inst.status, inst.detail = ST_STOPPED, t("Cerrada por el usuario")
        log.info(t("%s: instancia cerrada por el usuario"), inst.account.alias)
        self.changed.emit()

    def restart(self, inst_id: str) -> None:
        inst = self.get(inst_id)
        if not inst:
            return
        self._kill(inst)
        self._reset_for_launch(inst)
        inst.detail = t("Reinicio manual")
        log.info(t("%s: reinicio manual"), inst.account.alias)
        self._queue.put(inst.id)
        self.changed.emit()

    def remove(self, inst_id: str) -> None:
        with self._lock:
            inst = self._instances.get(inst_id)
            if inst and inst.status in ACTIVE_STATES:
                self.close(inst_id)
            self._instances.pop(inst_id, None)
        self.changed.emit()

    def close_all(self) -> None:
        for inst in self.snapshot():
            if inst.status not in (ST_STOPPED, ST_FAILED):
                self.close(inst.id)

    def minimize_all(self) -> None:
        for inst in self.snapshot():
            if inst.hwnd and winapi.is_window(inst.hwnd):
                winapi.minimize(inst.hwnd)

    def minimize(self, inst_id: str) -> None:
        inst = self.get(inst_id)
        if inst and winapi.is_window(inst.hwnd):
            winapi.minimize(inst.hwnd)
            self.changed.emit()

    def restore_all(self) -> None:
        for inst in self.window_instances():
            if winapi.is_minimized(inst.hwnd):
                winapi.show_no_activate(inst.hwnd)
        self.changed.emit()

    def ordered(self) -> list[Instance]:
        """Las instancias en el orden elegido en «Organizar ventanas»."""
        instances = self.snapshot()
        order = self.cfg.get("windows.order", "list")
        if order == "account":
            instances.sort(key=lambda i: i.account.alias.casefold())
        elif order == "game":
            instances.sort(key=lambda i: ((i.profile_name or i.target.label).casefold(),
                                          i.account.alias.casefold()))
        return instances

    def window_instances(self, include_minimized: bool = True) -> list[Instance]:
        return [i for i in self.ordered() if winapi.is_window(i.hwnd)
                and (include_minimized or not winapi.is_minimized(i.hwnd))]

    def move_in_list(self, inst_id: str, delta: int) -> None:
        with self._lock:
            ids = list(self._instances)
            old = ids.index(inst_id)
            new = max(0, min(old + delta, len(ids) - 1))
            ids.insert(new, ids.pop(old))
            self._instances = {i: self._instances[i] for i in ids}
        self.changed.emit()

    def arrange(self, manual: bool = True) -> None:
        """Ordena las ventanas en otro hilo: una ventana colgada no debe congelar la aplicación."""
        threading.Thread(target=self._arrange, args=(manual,), name="ventanas", daemon=True).start()

    def _arrange(self, manual: bool) -> None:
        if not self._arrange_lock.acquire(blocking=False):
            return
        try:
            # Al ordenar solas, las minimizadas se quedan como están
            hwnds = [i.hwnd for i in self.window_instances(include_minimized=manual)]
            result = window_layout.arrange(hwnds, dict(self.cfg.section("windows")))
        except Exception:
            log.exception("Fallo al ordenar las ventanas")
            return
        finally:
            self._arrange_lock.release()
        log.info(t("%d ventanas ordenadas"), result.placed)
        if manual:
            self._report_arrange(result)
        self.changed.emit()

    def _report_arrange(self, result: window_layout.ArrangeResult) -> None:
        if not result.placed:
            self.notify.emit("warning", t("No hay ninguna ventana que ordenar"))
        elif result.limited:
            self.notify.emit("warning", t("Algunas ventanas no aceptan un tamaño tan pequeño: se usó el más pequeño posible"))
        elif result.overlap:
            self.notify.emit("warning", t("No caben todas en el monitor con ese tamaño: algunas quedan superpuestas"))
        else:
            self.notify.emit("info", t("{0} ventanas ordenadas", result.placed))

    def resize_window(self, inst_id: str, width: int, height: int) -> None:
        inst = self.get(inst_id)
        if inst and winapi.is_window(inst.hwnd):
            threading.Thread(target=window_layout.resize, args=(inst.hwnd, width, height), name="ventanas",
                             daemon=True).start()

    def maximize(self, inst_id: str) -> None:
        inst = self.get(inst_id)
        if inst and winapi.is_window(inst.hwnd):
            winapi.maximize(inst.hwnd)

    def apply_performance(self) -> None:
        """Guarda los ajustes en los archivos de Roblox y aplica al momento los del procesador."""
        performance.apply(self.cfg)
        procs = list(self._procs.values())
        for index, proc in enumerate(procs):
            self._limit_process(proc, index)
        self.cfg.save_if_dirty()
        self.notify.emit("info", t("Ajustes aplicados. Reinicia las ventanas abiertas para ver los cambios de "
                                   "FPS y gráficos.") if procs else t("Ajustes aplicados a las próximas ventanas"))

    def _limit_process(self, proc: psutil.Process, index: int) -> None:
        """Prioridad, modo de eficiencia y núcleos: lo mismo que se puede cambiar desde el Administrador de tareas."""
        section = self.cfg.section("performance")
        total = psutil.cpu_count() or 1
        cores = int(section.get("cores") or 0)
        # Cada ventana usa núcleos distintos para que no se estorben entre ellas
        allowed = ([(index * cores + i) % total for i in range(cores)] if 0 < cores < total else list(range(total)))
        try:
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if section.get("low_priority") else psutil.NORMAL_PRIORITY_CLASS)
            proc.cpu_affinity(allowed)
        except psutil.Error as exc:
            log.warning(t("No se pudieron cambiar los límites del proceso %s: %s"), proc.pid, exc)
        winapi.set_efficiency_mode(proc.pid, bool(section.get("efficiency")))

    def focus(self, inst_id: str) -> bool:
        inst = self.get(inst_id)
        return bool(inst and inst.hwnd and winapi.focus_window(inst.hwnd))

    def update_account(self, account: Account) -> None:
        """Mantiene la copia en memoria de las instancias al editar una cuenta."""
        with self._lock:
            for inst in self._instances.values():
                if inst.account.id == account.id:
                    inst.account = account

    def set_multi_instance(self, enabled: bool) -> None:
        if enabled:
            self._prepare_multi_instance()
        else:
            self.mutex.release()

    # ------------------------------------------------------------------ internos
    def _emit(self, level: str, text: str) -> None:
        getattr(log, "error" if level == "error" else "warning" if level == "warning" else "info")(text)
        self.notify.emit(level, text)

    def _kill(self, inst: Instance) -> None:
        # Solo el objeto psutil guardado al lanzar: comprueba la identidad del proceso y así
        # nunca cierra otro programa que haya heredado el mismo PID.
        proc = self._procs.pop(inst.pid, None) if inst.pid else None
        if proc is not None:
            try:
                proc.kill()
            except psutil.Error:
                pass

    def _prepare_multi_instance(self) -> None:
        if launcher.close_tray_agents(self._claimed_pids()):
            self.mutex.release()  # lo tenía la bandeja: hay que volver a crearlo para que sea nuestro
        self.mutex.acquire()

    def _reset_for_launch(self, inst: Instance) -> None:
        inst.pid = inst.hwnd = None
        inst.status = ST_LAUNCHING
        inst.user_closed = False
        inst.log_path, inst.log_offset = None, 0
        inst.joined_at = inst.last_disconnect_at = 0.0
        inst.cpu = inst.ram_mb = 0.0
        inst.started_at = time.time()

    def _claimed_pids(self) -> set[int]:
        with self._lock:
            return {i.pid for i in self._instances.values() if i.pid}

    # ------------------------------------------------------------------ hilo lanzador
    def _launch_loop(self) -> None:
        last_launch = 0.0
        while not self._stop.is_set():
            try:
                inst_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            inst = self.get(inst_id)
            if not inst or inst.user_closed and inst.status == ST_STOPPED:
                continue
            wait = float(self.cfg.get("launch.delay_s", 8)) - (time.time() - last_launch)
            if wait > 0:
                inst.detail = t("Esperando {0:.0f} s para lanzar", wait)
                self.changed.emit()
                self._stop.wait(wait)
            try:
                self._launch_one(inst)
            except roblox_api.RobloxAuthError as exc:
                inst.status, inst.detail = ST_FAILED, str(exc)
                self._emit("error", t("{0}: {1}. Actualiza la cookie en Cuentas.", inst.account.alias, exc))
            except Exception as exc:
                log.exception("Fallo al lanzar %s", inst.account.alias)
                self._handle_failure(inst, t("Error al lanzar: {0}", exc))
            last_launch = time.time()
            self.changed.emit()

    def _launch_one(self, inst: Instance) -> None:
        self._reset_for_launch(inst)
        acc, target = inst.account, inst.target
        if self.cfg.get("launch.multi_instance"):
            self._prepare_multi_instance()
        performance.apply(self.cfg)

        inst.detail = t("Preparando inicio de sesión")
        self.changed.emit()
        if acc.login_method == LOGIN_COOKIE:
            if not acc.cookie:
                raise roblox_api.RobloxAuthError(t("La cuenta no tiene cookie guardada"))
            if target.share_code and not target.private_link_code:
                target.place_id, target.private_link_code = roblox_api.resolve_share_link(acc.cookie, target.share_code)
            uri = launcher.build_player_uri(roblox_api.get_auth_ticket(acc.cookie), target)
        else:
            if target.share_code:
                raise ValueError(t("Los enlaces 'share' necesitan una cuenta con cookie para resolverse"))
            uri = launcher.build_deeplink(target)

        before = launcher.roblox_pids()
        inst.detail = t("Abriendo Roblox")
        self.changed.emit()
        launcher.open_uri(uri)
        log.info(t("%s: lanzando %s"), acc.alias, target.label)

        deadline = time.time() + float(self.cfg.get("launch.pid_timeout_s", 60))
        while time.time() < deadline and not self._stop.is_set():
            new = launcher.roblox_pids() - before - self._claimed_pids()
            if new:
                procs = []
                for pid in new:
                    try:
                        procs.append(psutil.Process(pid))
                    except psutil.Error:
                        pass
                if procs:
                    proc = max(procs, key=lambda p: p.create_time())
                    inst.pid = proc.pid
                    inst.started_at = proc.create_time()
                    self._procs[proc.pid] = proc
                    break
            time.sleep(0.5)
        if not inst.pid:
            raise RuntimeError(t("Roblox no se abrió a tiempo"))

        self._limit_process(self._procs[inst.pid], len(self._procs) - 1)
        inst.status, inst.detail = ST_OPEN, t("Cargando")
        log.info(t("%s: proceso %s abierto"), acc.alias, inst.pid)

    # ------------------------------------------------------------------ hilo monitor
    def _monitor_loop(self) -> None:
        while not self._stop.wait(MONITOR_INTERVAL):
            try:
                self._check_network()
                for inst in self.snapshot():
                    self._check_instance(inst)
                self._auto_arrange()
            except Exception:
                log.exception("Error en el monitor de instancias")
            self.changed.emit()

    def _auto_arrange(self) -> None:
        pending, self._arrange_pending = self._arrange_pending, False
        if pending and self.cfg.get("windows.auto_arrange") and not self.cfg.get("launch.auto_minimize"):
            self.arrange(manual=False)

    def _check_network(self) -> None:
        if not self.cfg.get("reconnect.check_internet"):
            self.online = True
            return
        now = time.time()
        if now - self._last_net_check < NET_CHECK_EVERY:
            return
        self._last_net_check = now
        was = self.online
        self.online = internet_ok()
        if was and not self.online:
            self._emit("warning", t("Se perdió la conexión a internet"))
        elif not was and self.online:
            self._emit("info", t("Conexión a internet recuperada"))

    def _check_instance(self, inst: Instance) -> None:
        now = time.time()
        rc = self.cfg.section("reconnect")

        if inst.status in (ST_STOPPED, ST_FAILED, ST_DISCONNECTED, ST_CLOSED):
            return
        if inst.status in (ST_WAIT_RECONNECT, ST_WAIT_NET):
            if not self.online:
                inst.status, inst.detail = ST_WAIT_NET, t("Esperando a que vuelva internet")
                return
            if now >= inst.next_retry_at:
                self._reset_for_launch(inst)
                inst.detail = t("Reconectando (intento {0}/{1})", inst.retries, rc['max_attempts'])
                self._queue.put(inst.id)
            else:
                inst.status = ST_WAIT_RECONNECT
                inst.detail = t("Intento {0}/{1} en {2:.0f} s", inst.retries, rc['max_attempts'], inst.next_retry_at - now)
            return
        if inst.pid is None:
            return  # aún lo está lanzando el otro hilo

        proc = self._procs.get(inst.pid)
        try:
            alive = proc is not None and proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            alive = False
        if not alive:
            self._procs.pop(inst.pid, None)
            if not inst.user_closed:
                self._handle_failure(inst, t("El proceso de Roblox se cerró"))
            return
        try:
            inst.cpu = proc.cpu_percent(None) / psutil.cpu_count()
            inst.ram_mb = proc.memory_info().rss / 1_048_576
        except psutil.Error:
            pass

        # Ventana principal
        if not winapi.is_window(inst.hwnd):
            inst.hwnd = winapi.main_window_for_pid(inst.pid)
            if inst.hwnd:
                if self.cfg.get("launch.rename_windows"):
                    winapi.set_title(inst.hwnd, f"Roblox - {inst.account.alias}")
                if self.cfg.get("launch.auto_minimize"):
                    winapi.minimize(inst.hwnd)
                self._arrange_pending = True

        # Diálogos nativos de error/crash
        dialogs = winapi.error_dialogs_for_pid(inst.pid)
        if dialogs:
            title = dialogs[0]["title"] or t("sin título")
            self._handle_failure(inst, t("Diálogo de error: «{0}»", title))
            return

        # Log del cliente (archivo de texto) para saber si está en juego o desconectado
        self._read_client_log(inst, now)

        grace = float(rc.get("disconnect_grace_s", 25))
        if inst.last_disconnect_at and inst.last_disconnect_at > inst.joined_at:
            waited = now - inst.last_disconnect_at
            if waited >= grace:
                self._handle_failure(inst, t("Desconectado del servidor"), disconnected=True)
                return
            inst.detail = t("Posible desconexión ({0:.0f} s)", grace - waited)

        if inst.joined_at and inst.joined_at >= inst.last_disconnect_at:
            if inst.status != ST_INGAME:
                inst.status, inst.detail = ST_INGAME, ""
                log.info(t("%s: en juego (%s)"), inst.account.alias, inst.target.label)
                self._arrange_pending = True  # al terminar de cargar, Roblox puede cambiar su ventana
                self.joined.emit(inst.id)
            if inst.retries and now - inst.joined_at > float(rc.get("reset_after_s", 300)):
                inst.retries = 0
        elif inst.status == ST_INGAME:
            inst.status = ST_OPEN

        timeout = float(rc.get("join_timeout_s", 180))
        if (inst.log_path and inst.status != ST_INGAME and not inst.joined_at
                and rc.get("restart_on_join_timeout") and now - inst.started_at > timeout):
            self._handle_failure(inst, t("No entró al juego en {0:.0f} s", timeout))

    def _read_client_log(self, inst: Instance, now: float) -> None:
        if not inst.log_path:
            if now - inst.started_at > 120:
                return
            with self._lock:
                claimed = {i.log_path for i in self._instances.values() if i.log_path}
            inst.log_path = launcher.find_log_for_process(inst.started_at, claimed)
            if not inst.log_path:
                return
        try:
            with open(inst.log_path, "r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(inst.log_offset)
                chunk = fh.read()
                inst.log_offset = fh.tell()
        except OSError:
            return
        for idx, line in enumerate(chunk.splitlines()):
            kind = classify_log_line(line)
            stamp = now + idx * 1e-6  # conserva el orden de las líneas del mismo bloque
            if kind == "joined":
                inst.joined_at = stamp
            elif kind == "disconnect":
                inst.last_disconnect_at = stamp
            elif kind == "joining" and inst.status == ST_INGAME:
                inst.detail = t("Teletransportando")

    # ------------------------------------------------------------------ reconexión
    def _handle_failure(self, inst: Instance, reason: str, disconnected: bool = False) -> None:
        rc = self.cfg.section("reconnect")
        self._kill(inst)
        inst.pid = inst.hwnd = None
        self._emit("warning", f"{inst.account.alias}: {reason}")

        if not (rc.get("enabled") and inst.auto_reconnect):
            inst.status = ST_DISCONNECTED if disconnected else ST_ERROR
            inst.detail = reason
            return
        if not self.online:
            inst.status, inst.detail = ST_WAIT_NET, t("Esperando a que vuelva internet")
            inst.next_retry_at = time.time()
            return
        if inst.retries >= int(rc.get("max_attempts", 5)):
            inst.status, inst.detail = ST_FAILED, t("Sin éxito tras {0} intentos: {1}", inst.retries, reason)
            self._emit("error", t("{0}: se agotaron los intentos de reconexión", inst.account.alias))
            return
        delay = backoff_delay(inst.retries, float(rc.get("base_delay_s", 10)), float(rc.get("max_delay_s", 300)))
        inst.retries += 1
        inst.next_retry_at = time.time() + delay
        inst.status = ST_WAIT_RECONNECT
        inst.detail = t("Intento {0}/{1} en {2:.0f} s", inst.retries, rc['max_attempts'], delay)
        log.info(t("%s: reconexión programada en %.0f s (intento %d)"), inst.account.alias, delay, inst.retries)
