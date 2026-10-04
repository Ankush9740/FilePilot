; Inno Setup 6.7.3 configuration; build.ps1 supplies absolute input/output paths.
; These defaults also allow compiling this script directly from its directory.
#ifndef DistributionDir
  #define DistributionDir SourcePath + "..\dist\FilePilot"
#endif
#ifndef InstallerOutputDir
  #define InstallerOutputDir SourcePath + "..\dist\installer"
#endif
#define AppVersion "1.0.0"

[Setup]
AppId={{E77A7E3B-BACA-4C38-A5C7-7EDE9758BF4B}
AppName=FilePilot
AppVersion={#AppVersion}
AppVerName=FilePilot {#AppVersion}
DefaultDirName={localappdata}\Programs\FilePilot
DefaultGroupName=FilePilot
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#InstallerOutputDir}
OutputBaseFilename=FilePilot-Setup-{#AppVersion}
SetupIconFile=assets\FilePilot.ico
UninstallDisplayIcon={app}\FilePilot.exe
VersionInfoVersion=1.0.0.0
VersionInfoProductName=FilePilot
VersionInfoDescription=FilePilot Setup
VersionInfoProductVersion={#AppVersion}
Compression=lzma2/normal
SolidCompression=no
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DistributionDir}\*"; DestDir: "{app}"; Excludes: ".filepilot-packaging-owned"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FilePilot"; Filename: "{app}\FilePilot.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\FilePilot"; Filename: "{app}\FilePilot.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FilePilot.exe"; Description: "Launch FilePilot"; Flags: nowait postinstall skipifsilent

; No UninstallDelete entries: %LOCALAPPDATA%\FilePilot history/preferences survive.
; No PATH changes, associations, shell extensions, services, or network actions.
