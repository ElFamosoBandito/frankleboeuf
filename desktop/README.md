# frankleboeuf

Application Python locale de suivi du regard :

- **Fenêtre caméra** : retour webcam avec repères oculaires discrets.
- **Popup vidéo** : fenêtre simple au premier plan (avec audio) qui s'ouvre dès que vos yeux quittent l'écran et disparaît dès votre retour.

## Lancement

Nécessite **Python 3.10, 3.11 ou 3.12**.

- **Windows** : double-cliquez sur `lancer_windows.bat`
- **macOS / Linux** :
  ```bash
  chmod +x lancer_mac_linux.sh
  ./lancer_mac_linux.sh
  ```

Au premier lancement, l'environnement `.venv`, les dépendances et le modèle MediaPipe `face_landmarker.task` sont installés automatiquement.

## Vidéo d'alerte

Placez ou remplacez votre fichier vidéo (`.mp4`, `.mov`, `.webm`) dans le dossier `video/`.

## Raccourcis clavier (fenêtre caméra active)

- `c` : calibrer le centre de l'écran
- `g` : calibrer le bord gauche de l'écran
- `d` : calibrer le bord droit de l'écran
- `b` : calibrer le bas d'écran / clavier
- `r` : réinitialiser la calibration
- `q` / `Échap` : quitter

## Configuration locale

Au premier lancement, les valeurs de `config.example.json` sont utilisées si `config.json` n’existe pas. L’application enregistre ensuite les réglages locaux, la calibration et la position de la fenêtre dans `config.json`. Ce fichier est exclu de Git pour éviter de publier les préférences personnelles.

Pour personnaliser les réglages avant le lancement, copiez `config.example.json` vers `config.json`. Les principaux champs sont `awayDelayMs`, `returnDelayMs`, `sensitivity` (`strict`, `normal`, `relaxed`), `headCompensation`, `allowKeyboardGlance`, `cameraIndex`, `videoFile` et `videoUrl`. Un fichier local est prioritaire sur une URL distante. Les liens vers des pages YouTube ne sont pas des fichiers vidéo directement lisibles par le lecteur desktop ; utilisez un fichier local ou une URL vidéo directe.

Le modèle `face_landmarker.task` et l’environnement `.venv/` sont des ressources locales exclues de Git. Le lanceur les recrée si nécessaire. Après une mise à jour des dépendances, utilisez le Python de `.venv` avec `-m pip install -r requirements.txt`.
