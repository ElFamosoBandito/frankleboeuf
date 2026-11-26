# frankleboeuf

Application Python locale de suivi du regard par webcam. Une fenêtre affiche le retour caméra ; une popup vidéo avec audio s’ouvre lorsque les yeux quittent l’écran et disparaît au retour du regard.

## Prérequis

- Python 3.10, 3.11 ou 3.12.
- Une webcam et l’autorisation d’y accéder.
- Une connexion Internet au premier lancement pour installer les dépendances et télécharger le modèle de détection.

## Lancement

**Windows** : double-cliquez sur `desktop/lancer_windows.bat`.

**macOS / Linux** : depuis la racine du projet :

```bash
bash desktop/lancer_mac_linux.sh
```

Le lanceur crée automatiquement l’environnement `.venv` et installe les dépendances Python. Le modèle MediaPipe est téléchargé s’il est absent. L’application ouvre directement ses fenêtres sur l’ordinateur.

Une vidéo est fournie dans `desktop/video/`. Vous pouvez la remplacer par un fichier `.mp4`, `.mov` ou `.webm`. Les fichiers vidéo locaux sont prioritaires sur une URL distante.

## Utilisation et configuration

Dans la fenêtre caméra :

- `c` : calibrer le centre de l’écran.
- `g` / `d` : calibrer les bords gauche et droit.
- `b` : calibrer le bas de l’écran / clavier.
- `r` : réinitialiser la calibration.
- `q` / `Échap` : quitter.

Les valeurs initiales sont définies dans `desktop/config.example.json`. Pour personnaliser les réglages, copiez ce fichier vers `desktop/config.json`. L’application utilise ce fichier local pour sauvegarder la calibration et la position de la popup.

Consultez [la documentation desktop](desktop/README.md) pour les champs de configuration et les détails du lancement.

## Confidentialité

Les images de la webcam sont traitées localement, sans enregistrement ni envoi par l’application. Le modèle de détection est téléchargé depuis Google Cloud Storage si nécessaire. Une URL vidéo distante contacte son fournisseur.

Les réglages personnels (`desktop/config.json`), l’environnement Python, le modèle téléchargé, les caches et les fichiers `.env` sont exclus de Git. La vidéo fournie est conservée dans le dépôt ; les autres fichiers ajoutés dans `desktop/video/` sont ignorés pour éviter de publier des vidéos personnelles.

## Structure

- `desktop/frankleboeuf.py` : détection du regard, calibration et fenêtres de l’application.
- `desktop/lancer_windows.bat` : lanceur Windows.
- `desktop/lancer_mac_linux.sh` : lanceur macOS / Linux.
- `desktop/requirements.txt` : dépendances Python.
- `desktop/config.example.json` : configuration initiale partageable.
- `desktop/video/` : vidéo d’alerte fournie.
- `.github/workflows/checks.yml` : vérification automatique de la syntaxe Python et du lanceur shell.

## Vérification du code

```bash
python3 -m py_compile desktop/frankleboeuf.py
bash -n desktop/lancer_mac_linux.sh
```

Les changements de détection ou de lecture vidéo doivent aussi être vérifiés avec une webcam et une vidéo sur le système cible.
