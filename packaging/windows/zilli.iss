; Zilli Windows kurulumu (Inno Setup 6.2.2; Windows 7 ve sonrası).
; Yönetici istemez: kullanıcı klasörüne kurar, böylece ayarlar ve ses klasörleri yazılabilir kalır.
#define AppVersion GetEnv("ZILLI_VERSION")
[Setup]
AppId={{9C4B2E71-3D5A-4F86-B0E2-7A1C5D9F3B64}
AppName=Zilli
AppVersion={#AppVersion}
AppPublisher=Gökay
DefaultDirName={autopf}\Zilli
DefaultGroupName=Zilli
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Zilli-Kurulum-{#AppVersion}
SetupIconFile=..\..\assets\zilli.ico
UninstallDisplayIcon={app}\Zilli.exe
Compression=lzma2
SolidCompression=yes
MinVersion=6.1sp1
CloseApplications=force
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "autostart"; Description: "Bilgisayar açılınca Zilli otomatik başlasın (önerilir)"
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"

[Files]
Source: "..\..\build\win\Zilli\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; mevcut ses dosyalarının üzerine yazma (kullanıcı değiştirmiş olabilir)
Source: "..\..\build\win\sounds\*"; DestDir: "{app}"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs skipifsourcedoesntexist

[Dirs]
Name: "{app}\Müzik"

#include "..\..\build\win\installdelete.iss"

[Icons]
Name: "{group}\Zilli"; Filename: "{app}\Zilli.exe"
Name: "{autodesktop}\Zilli"; Filename: "{app}\Zilli.exe"; Tasks: desktopicon

[Registry]
; Zilli'nin Ayarlar sayfasındaki "açılınca başlasın" düğmesi de aynı değeri kullanır
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Zilli"; ValueData: """{app}\Zilli.exe"" --min"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Zilli.exe"; Description: "Zilli'yi şimdi başlat"; Flags: nowait postinstall skipifsilent
