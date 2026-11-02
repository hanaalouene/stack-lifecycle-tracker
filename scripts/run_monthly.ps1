# Local run for Windows Task Scheduler. SMTP_* and MAIL_TO must be set as user environment variables.
Set-Location (Split-Path -Parent $PSScriptRoot)
python run.py run *>> logs\run.log
