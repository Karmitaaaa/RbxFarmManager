; Full installer for RbxFarm Manager (Inno Setup 6). Built by build.bat:
;   ISCC /DAppVersion=1.1.0 /DBuildDir=<Build folder> installer\RbxFarmManager.iss
; Per-user install (no admin rights). Accounts and settings in %APPDATA%\RbxFarmManager are kept on
; uninstall and on update. The app's in-app updater runs this installer with
;   /SILENT /SUPPRESSMSGBOXES /CLOSEAPPLICATIONS /RELAUNCH=1
; which waits for the app to close, updates it and opens it again.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\..\Build"
#endif
#define AppName "RbxFarm Manager"
#define AppExe "RbxFarmManager.exe"
#define AppMutex "RbxFarmManagerAppMutex"

[Setup]
AppId={{E740EDDA-2D96-418E-8452-AC11AE2065EA}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Karmitaaaa
AppPublisherURL=https://github.com/Karmitaaaa/RbxFarmManager
AppSupportURL=https://github.com/Karmitaaaa/RbxFarmManager/issues
AppUpdatesURL=https://github.com/Karmitaaaa/RbxFarmManager/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#BuildDir}\Instalador
OutputBaseFilename=RbxFarmManager-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
ShowLanguageDialog=no
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.CloseApp=RbxFarm Manager is running.%n%nClose it (tray icon → Salir/Exit) and click Retry.
spanish.CloseApp=RbxFarm Manager está abierto.%n%nCiérralo (icono de la bandeja → Salir) y pulsa Reintentar.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#BuildDir}\RbxFarmManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove the previous version's bundled libraries so no stale files remain after an update
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: IsRelaunch

[Code]
function IsRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

{ The app holds a named mutex while open. During an in-app update we wait for it to close on its own;
  otherwise we ask the user to close it. }
function WaitForAppToClose(WaitMs: Integer): Boolean;
var
  Waited: Integer;
begin
  Waited := 0;
  while CheckForMutexes('{#AppMutex}') and (Waited < WaitMs) do
  begin
    Sleep(500);
    Waited := Waited + 500;
  end;
  while CheckForMutexes('{#AppMutex}') do
  begin
    if SuppressibleMsgBox(CustomMessage('CloseApp'), mbError, MB_RETRYCANCEL, IDCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
  Result := True;
end;

function InitializeSetup: Boolean;
begin
  if IsRelaunch then
    Result := WaitForAppToClose(30000)
  else
    Result := WaitForAppToClose(0);
end;

function InitializeUninstall: Boolean;
begin
  Result := WaitForAppToClose(0);
end;
