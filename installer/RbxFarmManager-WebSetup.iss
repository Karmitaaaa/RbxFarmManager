; Web installer for RbxFarm Manager (Inno Setup 6). A small setup that downloads the latest full
; installer from GitHub Releases and runs it, so it always installs the newest version.
;   ISCC /DBuildDir=<Build folder> installer\RbxFarmManager-WebSetup.iss

#ifndef BuildDir
  #define BuildDir "..\..\Build"
#endif
#define AppName "RbxFarm Manager"
#define AppExe "RbxFarmManager.exe"
#define MainAppId "{E740EDDA-2D96-418E-8452-AC11AE2065EA}"
#define DownloadUrl "https://github.com/Karmitaaaa/RbxFarmManager/releases/latest/download/RbxFarmManager-Setup.exe"

[Setup]
AppId={{3B0F4C52-9E8A-4C67-8F0E-6D2A1B7C9E41}
AppName={#AppName}
AppVersion=latest
AppPublisher=Karmitaaaa
AppPublisherURL=https://github.com/Karmitaaaa/RbxFarmManager
CreateAppDir=no
Uninstallable=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir={#BuildDir}\Instalador
OutputBaseFilename=RbxFarmManager-WebSetup
SetupIconFile=..\assets\icon.ico
ShowLanguageDialog=no
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.WelcomeNote=This installer downloads the latest version of RbxFarm Manager from GitHub (about 120 MB) and installs it.
spanish.WelcomeNote=Este instalador descarga de GitHub la última versión de RbxFarm Manager (unos 120 MB) y la instala.
english.InstallFailed=The installation did not finish (code %1). Try again or download the full installer from GitHub.
spanish.InstallFailed=La instalación no terminó (código %1). Vuelve a intentarlo o descarga el instalador completo desde GitHub.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{code:InstalledExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent; Check: HasInstalledExe

[Code]
var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := WizardForm.WelcomeLabel2.Caption + #13#10#13#10 + CustomMessage('WelcomeNote');
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#DownloadUrl}', 'RbxFarmManager-Setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        if not DownloadPage.AbortedByUser then
          SuppressibleMsgBox(AddPeriod(GetExceptionMessage), mbCriticalError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Params: String;
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    Params := '/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LANG=' + ActiveLanguage;
    if WizardIsTaskSelected('desktopicon') then
      Params := Params + ' /TASKS="desktopicon"'
    else
      Params := Params + ' /TASKS=""';
    if not Exec(ExpandConstant('{tmp}\RbxFarmManager-Setup.exe'), Params, '', SW_SHOW,
                ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      SuppressibleMsgBox(FmtMessage(CustomMessage('InstallFailed'), [IntToStr(ResultCode)]),
                         mbCriticalError, MB_OK, IDOK);
  end;
end;

{ Where the full installer put the app (same AppId as RbxFarmManager.iss). }
function InstalledExe(Param: String): String;
var
  Location: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MainAppId}_is1',
                         'InstallLocation', Location) or
     RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MainAppId}_is1',
                         'InstallLocation', Location) then
    Result := AddBackslash(Location) + '{#AppExe}';
end;

function HasInstalledExe: Boolean;
begin
  Result := (InstalledExe('') <> '') and FileExists(InstalledExe(''));
end;
