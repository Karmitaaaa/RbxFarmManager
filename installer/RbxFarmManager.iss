; Instalador de RbxFarm Manager (Inno Setup 6). Lo compila build.bat:
;   ISCC /DAppVersion=1.0.0 /DBuildDir=<carpeta Build> installer\RbxFarmManager.iss
; Se instala solo para el usuario actual (no pide permisos de administrador).
; Tus cuentas y ajustes (%APPDATA%\RbxFarmManager) no se borran al desinstalar.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\..\Build"
#endif
#define AppName "RbxFarm Manager"
#define AppExe "RbxFarmManager.exe"

[Setup]
AppId={{E740EDDA-2D96-418E-8452-AC11AE2065EA}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=RbxFarm
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#BuildDir}\Instalador
OutputBaseFilename=RbxFarmManager-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
; El programa crea este mutex al abrirse: el instalador pide cerrarlo antes de actualizar o desinstalar
AppMutex=RbxFarmManagerAppMutex
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#BuildDir}\RbxFarmManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
