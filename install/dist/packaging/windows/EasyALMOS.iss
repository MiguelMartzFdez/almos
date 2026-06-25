#define MyAppName "EasyALMOS"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "The Alegre Group"
#define MyAppIcon "assets\almos_icon.ico"
#define MiniforgeInstaller "assets\Miniforge3-Windows-x86_64.exe"
#define DependencyHelper "scripts\install_easyalmos.ps1"
#define UninstallHelper "scripts\uninstall_easyalmos.ps1"
#define SharedEnvFile "..\shared\almos.yaml"
#define GuiLauncher "scripts\launch_easyalmos.pyw"
#define MyAppIconName "almos_icon.ico"
#define MiniforgeInstallerName "Miniforge3-Windows-x86_64.exe"
#define DependencyHelperName "install_easyalmos.ps1"
#define UninstallHelperName "uninstall_easyalmos.ps1"
#define SharedEnvFileName "almos.yaml"
#define GuiLauncherName "launch_easyalmos.pyw"

[Setup]
AppId={{80A5B503-8F72-4CB2-B695-7E5E922E4624}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\windows
OutputBaseFilename=easyalmos-{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppIconName}
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
ChangesEnvironment=no
ChangesAssociations=no
AllowCancelDuringInstall=yes
ExtraDiskSpaceRequired=4000000000

[Dirs]
Name: "{app}\logs"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#MiniforgeInstaller}"; Flags: dontcopy
Source: "{#SharedEnvFile}"; Flags: dontcopy
Source: "{#DependencyHelper}"; Flags: dontcopy
Source: "{#GuiLauncher}"; DestDir: "{app}"; DestName: "{#GuiLauncherName}"; Flags: ignoreversion
Source: "{#UninstallHelper}"; DestDir: "{app}"; DestName: "{#UninstallHelperName}"; Flags: ignoreversion
Source: "{#MyAppIcon}"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\miniforge\envs\almos\pythonw.exe"; Parameters: """{app}\{#GuiLauncherName}"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon
Name: "{userprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\miniforge\envs\almos\pythonw.exe"; Parameters: """{app}\{#GuiLauncherName}"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"

[Code]
type
  TWindowsMessage = record
    WindowHandle: LongWord;
    MessageId: LongWord;
    WParam: LongWord;
    LParam: LongInt;
    MessageTime: LongWord;
    PointX: LongInt;
    PointY: LongInt;
  end;

var
  DependencyPage: TWizardPage;
  DependencyStatusLabel: TNewStaticText;
  DependencyDetailLabel: TNewStaticText;
  DependencyProgress: TNewProgressBar;
  DependencyRunning: Boolean;
  DependencyComplete: Boolean;
  DependencyFailed: Boolean;
  DependencyStarted: Boolean;
  SetupCompleted: Boolean;
  ClosingAfterDependencyCancel: Boolean;
  ClosingAfterDependencyFailure: Boolean;
  DependencyCancelRequested: Boolean;
  DependencyStateDir: String;
  DependencyPidFile: String;
  DependencyPhaseFile: String;
  DependencySuccessFile: String;
  DependencyFailureFile: String;
  FinishedWarningLabel: TNewStaticText;
  UninstallCleanupRunning: Boolean;
  UninstallCleanupStateDir: String;
  UninstallCleanupSuccessFile: String;
  UninstallCleanupFailureFile: String;

function PeekMessage(
  var Msg: TWindowsMessage; WindowHandle: LongWord;
  FilterMin, FilterMax, RemoveMode: LongWord): Boolean;
  external 'PeekMessageW@user32.dll stdcall';
function TranslateMessage(const Msg: TWindowsMessage): Boolean;
  external 'TranslateMessage@user32.dll stdcall';
function DispatchMessage(const Msg: TWindowsMessage): LongInt;
  external 'DispatchMessageW@user32.dll stdcall';

procedure ProcessPendingMessages;
var
  Msg: TWindowsMessage;
begin
  while PeekMessage(Msg, 0, 0, 0, 1) do
  begin
    TranslateMessage(Msg);
    DispatchMessage(Msg);
  end;
end;

procedure SetDependencyProgressMarquee;
begin
  DependencyProgress.Style := npbstMarquee;
  DependencyProgress.Min := 0;
  DependencyProgress.Max := 100;
  DependencyProgress.Position := 0;
end;

procedure SetDependencyProgressComplete(const ErrorState: Boolean);
begin
  DependencyProgress.Style := npbstNormal;
  DependencyProgress.Min := 0;
  DependencyProgress.Max := 100;
  DependencyProgress.Position := DependencyProgress.Max;
  if ErrorState then
    DependencyProgress.State := npbsError
  else
    DependencyProgress.State := npbsNormal;
  DependencyProgress.Update;
end;

procedure SetUninstallProgressMarquee;
begin
  UninstallProgressForm.ProgressBar.Style := npbstMarquee;
  UninstallProgressForm.ProgressBar.Min := 0;
  UninstallProgressForm.ProgressBar.Max := 100;
  UninstallProgressForm.ProgressBar.Position := 0;
  UninstallProgressForm.ProgressBar.Update;
end;

function Quote(const Value: String): String;
begin
  Result := '"' + Value + '"';
end;

function GetAppDir: String;
begin
  if WizardSilent then
    Result := ExpandConstant('{app}')
  else
    Result := WizardForm.DirEdit.Text;
end;

procedure RemovePrivateRuntime(const RemoveLogs: Boolean);
var
  AppDir: String;
begin
  AppDir := GetAppDir;
  if AppDir = '' then
    Exit;

  { These are the only external directories created by this installer. }
  DelTree(AddBackslash(AppDir) + 'miniforge', True, True, True);
  if RemoveLogs then
    DelTree(AddBackslash(AppDir) + 'logs', True, True, True);
end;

procedure StopDependencyProcess;
var
  Pid: String;
  PidData: AnsiString;
  ResultCode: Integer;
begin
  if LoadStringFromFile(DependencyPidFile, PidData) then
  begin
    Pid := Trim(String(PidData));
    if Pid <> '' then
    begin
      Log('Stopping EasyALMOS dependency process tree with PID ' + Pid);
      Exec(
        ExpandConstant('{sys}\taskkill.exe'),
        '/PID ' + Pid + ' /T /F',
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode);
    end;
  end;
end;

procedure UpdateDependencyStatus;
var
  Phase: String;
  PhaseData: AnsiString;
begin
  if not LoadStringFromFile(DependencyPhaseFile, PhaseData) then
    Exit;

  Phase := Trim(String(PhaseData));
  if Phase = 'miniforge' then
  begin
    DependencyStatusLabel.Caption :=
      'Step 1 of 4: Installing the private Miniforge distribution...';
    DependencyDetailLabel.Caption :=
      'This copy is isolated inside EasyALMOS and does not modify your Conda installation.';
  end
  else if Phase = 'environment' then
  begin
    DependencyStatusLabel.Caption :=
      'Step 2 of 3: Creating the Conda environment from almos.yaml...';
    DependencyDetailLabel.Caption :=
      'Conda is creating the ALMOS environment directly from the shared environment definition.';
  end
  else if Phase = 'validate' then
  begin
    DependencyStatusLabel.Caption :=
      'Step 3 of 3: Validating the EasyALMOS launcher...';
    DependencyDetailLabel.Caption :=
      'Checking that the GUI entry point was created correctly.';
  end;
  DependencyStatusLabel.Update;
  DependencyDetailLabel.Update;
end;

procedure StartDependencyInstall;
var
  PowerShellExe: String;
  Parameters: String;
  ResultCode: Integer;
  FailureText: String;
  FailureData: AnsiString;
begin
  { Every attempt starts from a clean EasyALMOS-owned runtime. }
  RemovePrivateRuntime(True);

  ExtractTemporaryFile('{#MiniforgeInstallerName}');
  ExtractTemporaryFile('{#SharedEnvFileName}');
  ExtractTemporaryFile('{#DependencyHelperName}');

  DependencyRunning := True;
  DependencyComplete := False;
  DependencyFailed := False;
  DependencyStarted := True;
  DependencyCancelRequested := False;

  DelTree(DependencyStateDir, True, True, True);
  ForceDirectories(DependencyStateDir);

  WizardForm.NextButton.Enabled := False;
  WizardForm.BackButton.Enabled := False;
  WizardForm.NextButton.Caption := '&Install';
  DependencyProgress.State := npbsNormal;
  SetDependencyProgressMarquee;
  DependencyStatusLabel.Caption := 'Installing EasyALMOS dependencies...';
  DependencyDetailLabel.Caption :=
    'Please wait. Installation can take 5 to 10 minutes on some systems and requires at least 4 GB of free disk space. You can safely stop this process using Cancel.';

  PowerShellExe := ExpandConstant(
    '{sys}\WindowsPowerShell\v1.0\powershell.exe');
  Parameters :=
    '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden ' +
    '-ExecutionPolicy Bypass -File ' +
    Quote(ExpandConstant('{tmp}\{#DependencyHelperName}')) +
    ' -InstallDir ' + Quote(WizardForm.DirEdit.Text) +
    ' -MiniforgeInstaller ' +
      Quote(ExpandConstant('{tmp}\{#MiniforgeInstallerName}')) +
    ' -EnvFile ' + Quote(ExpandConstant('{tmp}\{#SharedEnvFileName}')) +
    ' -StateDir ' + Quote(DependencyStateDir);

  Log('Starting clean EasyALMOS dependency installation.');
  if not Exec(
    PowerShellExe,
    Parameters,
    '',
    SW_HIDE,
    ewNoWait,
    ResultCode) then
  begin
    DependencyRunning := False;
    DependencyFailed := True;
    RemovePrivateRuntime(False);
    RaiseException(
      'The EasyALMOS dependency installer could not be started: ' +
      SysErrorMessage(ResultCode));
  end;

  while not FileExists(DependencySuccessFile) and
    not FileExists(DependencyFailureFile) and
    not DependencyCancelRequested do
  begin
    UpdateDependencyStatus;
    ProcessPendingMessages;
    Sleep(90);
  end;

  UpdateDependencyStatus;
  DependencyRunning := False;
  if DependencyCancelRequested then
  begin
    Log('Dependency installation cancelled by the user.');
    StopDependencyProcess;
    RemovePrivateRuntime(True);
    ClosingAfterDependencyCancel := True;
    WizardForm.Close;
    Exit;
  end;

  if FileExists(DependencySuccessFile) then
  begin
    DependencyComplete := True;
    DependencyFailed := False;
    SetDependencyProgressComplete(False);
    DependencyStatusLabel.Caption := 'EasyALMOS dependencies installed successfully.';
    DependencyDetailLabel.Caption :=
      'Click Next to copy the launcher and create the shortcuts.';
    WizardForm.NextButton.Caption := '&Next >';
    WizardForm.NextButton.Enabled := True;
    WizardForm.BackButton.Enabled := False;
  end;
  if FileExists(DependencyFailureFile) then
  begin
    DependencyComplete := False;
    DependencyFailed := True;
    RemovePrivateRuntime(False);
    SetDependencyProgressComplete(True);
    DependencyStatusLabel.Caption := 'The ALMOS environment could not be installed.';
    DependencyDetailLabel.Caption :=
      'Installation stopped. Diagnostic logs were kept for support.';
    WizardForm.NextButton.Enabled := False;
    WizardForm.BackButton.Enabled := False;
    WizardForm.CancelButton.Enabled := True;
    if LoadStringFromFile(DependencyFailureFile, FailureData) then
      FailureText := String(FailureData)
    else
      FailureText := 'The dependency helper failed without an error message.';
    MsgBox(
      Trim(FailureText) + #13#10 + #13#10 +
      'Diagnostic logs: ' + AddBackslash(WizardForm.DirEdit.Text) + 'logs' + #13#10 +
      'Contact: miguel.martinez@csic.es',
      mbError,
      MB_OK);
    ClosingAfterDependencyFailure := True;
    WizardForm.Close;
    Exit;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption :=
    'EasyALMOS installs its own private runtime automatically.' + #13#10#13#10 +
    'After you continue, setup and the first launch can take a few minutes on some systems.' + #13#10 +
    'If Windows takes a moment to respond, please wait and do not click again.';

  DependencyStateDir := ExpandConstant('{tmp}\EasyALMOSDependencyState');
  DependencyPidFile := AddBackslash(DependencyStateDir) + 'pid.txt';
  DependencyPhaseFile := AddBackslash(DependencyStateDir) + 'phase.txt';
  DependencySuccessFile := AddBackslash(DependencyStateDir) + 'success.flag';
  DependencyFailureFile := AddBackslash(DependencyStateDir) + 'failure.txt';
  DependencyPage := CreateCustomPage(
    wpReady,
    'Installing EasyALMOS dependencies',
    'Miniforge and the isolated almos environment will be installed now. This can take 5 to 10 minutes.');

  DependencyStatusLabel := TNewStaticText.Create(DependencyPage);
  DependencyStatusLabel.Parent := DependencyPage.Surface;
  DependencyStatusLabel.Left := 0;
  DependencyStatusLabel.Top := ScaleY(16);
  DependencyStatusLabel.Width := DependencyPage.SurfaceWidth;
  DependencyStatusLabel.Caption := 'Preparing the EasyALMOS installation...';

  DependencyProgress := TNewProgressBar.Create(DependencyPage);
  DependencyProgress.Parent := DependencyPage.Surface;
  DependencyProgress.Left := 0;
  DependencyProgress.Top := DependencyStatusLabel.Top + ScaleY(32);
  DependencyProgress.Width := DependencyPage.SurfaceWidth;
  DependencyProgress.Height := ScaleY(20);
  SetDependencyProgressMarquee;

  DependencyDetailLabel := TNewStaticText.Create(DependencyPage);
  DependencyDetailLabel.Parent := DependencyPage.Surface;
  DependencyDetailLabel.Left := 0;
  DependencyDetailLabel.Top := DependencyProgress.Top + ScaleY(36);
  DependencyDetailLabel.Width := DependencyPage.SurfaceWidth;
  DependencyDetailLabel.AutoSize := False;
  DependencyDetailLabel.WordWrap := True;
  DependencyDetailLabel.Height := ScaleY(48);
  DependencyDetailLabel.Caption :=
    'All installation steps will run in this window. Installation can take 5 to 10 minutes on some systems and requires at least 4 GB of free disk space.';

  FinishedWarningLabel := TNewStaticText.Create(WizardForm);
  FinishedWarningLabel.Parent := WizardForm.FinishedLabel.Parent;
  FinishedWarningLabel.Left := WizardForm.FinishedLabel.Left;
  FinishedWarningLabel.Top :=
    WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(20);
  FinishedWarningLabel.Width := WizardForm.FinishedLabel.Width;
  FinishedWarningLabel.Height := ScaleY(44);
  FinishedWarningLabel.AutoSize := False;
  FinishedWarningLabel.WordWrap := True;
  FinishedWarningLabel.Font.Style := [fsBold];
  FinishedWarningLabel.Caption := '';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = DependencyPage.ID then
  begin
    WizardForm.CancelButton.Enabled := True;
    if DependencyComplete then
    begin
      WizardForm.NextButton.Caption := '&Next >';
      WizardForm.NextButton.Enabled := True;
      WizardForm.BackButton.Enabled := False;
    end
    else if not DependencyRunning then
      StartDependencyInstall;
  end;

  if CurPageID = wpFinished then
  begin
    WizardForm.FinishedLabel.Caption :=
      'Setup has finished installing EasyALMOS on your computer.' + #13#10#13#10 +
      'You can launch it from the Start menu or by searching for "EasyALMOS" in Windows.';
    FinishedWarningLabel.Caption :=
      'IMPORTANT: The first launch of EasyALMOS may take a little longer while Windows prepares and scans the new environment. When you open it, an "EasyALMOS is opening..." message will appear and close automatically when the app is ready.';
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DependencyPage.ID then
  begin
    if DependencyComplete then
      Result := True
    else if DependencyFailed then
    begin
      StartDependencyInstall;
      Result := False;
    end
    else
      Result := False;
  end;
end;

function BackButtonClick(CurPageID: Integer): Boolean;
begin
  Result := not ((CurPageID = DependencyPage.ID) and DependencyRunning);
end;

procedure CancelButtonClick(
  CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if ClosingAfterDependencyCancel then
  begin
    Confirm := False;
    Cancel := True;
    Exit;
  end;

  if ClosingAfterDependencyFailure then
  begin
    Confirm := False;
    Cancel := True;
    Exit;
  end;

  if DependencyStarted and not SetupCompleted then
  begin
    Confirm := False;
    if MsgBox(
      'Cancel the EasyALMOS installation?' + #13#10 + #13#10 +
      'The current Miniforge/Conda process will be stopped and only the ' +
      'private EasyALMOS runtime will be removed.',
      mbConfirmation,
      MB_YESNO) = IDYES then
    begin
      if DependencyRunning then
      begin
        DependencyCancelRequested := True;
        DependencyStatusLabel.Caption := 'Cancelling and removing partial files...';
        DependencyStatusLabel.Update;
        Cancel := False;
      end
      else
      begin
        Cancel := True;
        RemovePrivateRuntime(not DependencyFailed);
      end;
    end
    else
      Cancel := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
    SetupCompleted := True;
end;

procedure DeinitializeSetup;
begin
  if DependencyStarted and not SetupCompleted then
  begin
    StopDependencyProcess;
    RemovePrivateRuntime(not DependencyFailed);
  end;
  DelTree(DependencyStateDir, True, True, True);
end;

function InitializeSetup(): Boolean;
begin
  DependencyRunning := False;
  DependencyComplete := False;
  DependencyFailed := False;
  DependencyStarted := False;
  SetupCompleted := False;
  ClosingAfterDependencyCancel := False;
  ClosingAfterDependencyFailure := False;
  DependencyCancelRequested := False;
  Result := True;
end;

procedure StartUninstallCleanup;
var
  PowerShellExe: String;
  Parameters: String;
  ResultCode: Integer;
  FailureData: AnsiString;
  FailureText: String;
begin
  if UninstallSilent then
    Exit;

  UninstallCleanupRunning := True;
  DelTree(UninstallCleanupStateDir, True, True, True);
  ForceDirectories(UninstallCleanupStateDir);

  UninstallProgressForm.StatusLabel.Caption :=
    'Removing the private EasyALMOS runtime...';
  UninstallProgressForm.StatusLabel.Update;

  PowerShellExe := ExpandConstant(
    '{sys}\WindowsPowerShell\v1.0\powershell.exe');
  Parameters :=
    '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden ' +
    '-ExecutionPolicy Bypass -File ' +
    Quote(AddBackslash(ExpandConstant('{app}')) + '{#UninstallHelperName}') +
    ' -InstallDir ' + Quote(ExpandConstant('{app}')) +
    ' -StateDir ' + Quote(UninstallCleanupStateDir);

  if not Exec(
    PowerShellExe,
    Parameters,
    '',
    SW_HIDE,
    ewNoWait,
    ResultCode) then
  begin
    Log('Could not start uninstall cleanup helper. Falling back to normal uninstall.');
    UninstallCleanupRunning := False;
    Exit;
  end;

  while not FileExists(UninstallCleanupSuccessFile) and
    not FileExists(UninstallCleanupFailureFile) do
  begin
    ProcessPendingMessages;
    Sleep(90);
  end;

  UninstallCleanupRunning := False;
  if LoadStringFromFile(UninstallCleanupFailureFile, FailureData) then
  begin
    FailureText := Trim(String(FailureData));
    if FailureText <> '' then
    begin
      MsgBox(
        'EasyALMOS runtime cleanup reported an issue:' + #13#10 + #13#10 +
        FailureText,
        mbInformation,
        MB_OK);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StartUninstallCleanup;
end;

procedure InitializeUninstallProgressForm;
begin
  UninstallCleanupStateDir := ExpandConstant('{tmp}\EasyALMOSUninstallState');
  UninstallCleanupSuccessFile :=
    AddBackslash(UninstallCleanupStateDir) + 'success.flag';
  UninstallCleanupFailureFile :=
    AddBackslash(UninstallCleanupStateDir) + 'failure.txt';
  SetUninstallProgressMarquee;
end;

procedure DeinitializeUninstall;
begin
  DelTree(UninstallCleanupStateDir, True, True, True);
end;
