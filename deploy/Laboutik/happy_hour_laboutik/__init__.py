# FR : Django 2.2 (LaBoutik) ne détecte pas seul l'AppConfig : sans cette ligne,
# ready() ne s'exécute pas et le happy hour n'est pas branché.
# EN: Django 2.2 does not auto-detect AppConfig; required for ready() to run.
default_app_config = 'happy_hour_laboutik.apps.HappyHourLaboutikConfig'
