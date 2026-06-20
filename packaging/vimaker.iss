; Inno Setup script for Vimaker (Windows installer).
; Build:  iscc packaging\vimaker.iss
; Expects the PyInstaller output at dist\Vimaker\ (with bundled ollama\ inside).

#define AppName "Vimaker"
#define AppVersion "0.1.0"
#define AppPublisher "Vimaker"
#define AppExe "Vimaker.exe"

[Setup]
AppId={{B5F2A0E2-9C3D-4E7A-9C2A-VIMAKER0001}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Vimaker-Setup-{#AppVersion}
SetupIconFile=..\src\vimaker\gui\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The bundled model blobs make this large; allow plenty of disk.
DiskSpanning=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Entire PyInstaller one-folder output, including the bundled ollama\ subfolder.
Source: "..\dist\Vimaker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
