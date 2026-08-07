# Arch's Auto Clipping — Documentation

Application qui lit des fichiers CSV, télécharge les vidéos YouTube associées, découpe des clips selon les horaires indiqués, puis archive les CSV traités.

> **Note GitHub :** les binaires volumineux (`ffmpeg`, Python Manager, etc.) **ne sont pas** dans le dépôt.  
> Ils sont téléchargés automatiquement par `install.bat` / `install.sh` dans le dossier `tools/`, ou installés via les liens ci-dessous.

---

## Windows (débutant)

### 1. Installer Python (une seule fois)

Les fichiers Python ne sont **pas** fournis dans le projet (trop volumineux pour GitHub).

#### Téléchargement

1. Ouvrez ce lien dans votre navigateur :  
   **[Python Install Manager 26.3 (MSIX) — site officiel](https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix)**  
   Page de la version : [Python install manager 26.3](https://www.python.org/downloads/release/pymanager-263/)  
   Ou page générale : [python.org/downloads](https://www.python.org/downloads/) → *Download Python install manager*
2. Enregistrez le fichier `python-manager-26.3.msix` (par ex. dans Téléchargements).
3. Double-cliquez sur **`python-manager-26.3.msix`** pour l’installer.

#### Questions à l’écran — réponses

| Question | Réponse |
|----------|---------|
| **Update setting now ?** | **Y** (Yes) |
| **Add commands directory to your PATH Now ?** | **Y** (Yes) |
| **Install the current latest version of CPython ?** | **Y** (Yes) |
| **View Help Online ?** | **N** (No) |

4. Fermez puis rouvrez l’Explorateur / le terminal pour que le PATH soit pris en compte.

### 2. Installer le programme (dépendances + outils)

1. Double-cliquez sur **`install.bat`**  
   (**pas** `install.sh` : c’est la version Linux).
2. Une fenêtre noire (terminal) s’ouvre.
3. Le script :
   - crée l’environnement Python local (`.venv`)
   - installe les librairies (`PySide6`, `yt-dlp`)
   - **télécharge automatiquement** dans `tools\` :
     - `ffmpeg.exe`
     - `ffprobe.exe`  
     (build Windows 64-bit, uniquement si absents)
4. **Appuyez sur une touche** pour continuer quand c’est demandé.
5. Le terminal se **ferme** à la fin.

### 3. Lancer le programme

1. Double-cliquez sur **`run.bat`**  
   (**pas** `run.sh` : c’est la version Linux).
2. Une fenêtre s’affiche : **Arch's Auto Clipping**.
3. Cliquez sur **Start** pour démarrer le traitement.

### 4. Utilisation courante (Windows)

| Bouton | Rôle |
|--------|------|
| **Start** | Lance le traitement des CSV du dossier `files` |
| **Pause** / **Resume** | Met en pause / reprend |
| **Stop** | Arrête le traitement (sans archiver les CSV) |

**Dossiers importants :**

| Dossier | Contenu |
|---------|---------|
| `files\` | Placez ici vos fichiers CSV à traiter |
| `download\` | Vidéos YouTube téléchargées |
| `clips\` | Clips découpés (un sous-dossier par vidéo) |
| `processeds\` | CSV déjà traités (archivés par date/heure) |
| `tools\` | Binaires téléchargés par `install.bat` (`ffmpeg.exe`, …) — **non versionnés sur GitHub** |

### Format CSV (rapide)

Colonnes requises : `videoTitle`, `videoUrl`, `startTime`, `endTime`  
(optionnel : `videoId`)

---

## Linux

### 1. Installer Python (CLI)

Sur **Debian / Ubuntu** :

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version   # doit afficher 3.10 ou plus
```

Sur **Fedora** :

```bash
sudo dnf install -y python3 python3-pip
```

Sur **Arch** :

```bash
sudo pacman -S python
```

Vérification :

```bash
python3 --version
```

### 2. Installer le programme

```bash
cd /chemin/vers/le/projet
chmod +x install.sh run.sh
./install.sh
```

Le script :

- crée un environnement virtuel `.venv`
- installe les dépendances Python (`PySide6`, `yt-dlp`)
- crée les dossiers `files/`, `download/`, `clips/`, `processeds/`, `tools/`
- **télécharge automatiquement** dans `tools/` (si absents) :
  - `ffmpeg`
  - `ffprobe`  
  (binaire statique Linux adapté à l’architecture)

### 3. Lancer le programme

```bash
./run.sh
```

Puis cliquez sur **Start** dans la fenêtre **Arch's Auto Clipping**.

### 4. Utilisation courante (Linux)

Même interface que sous Windows : **Start** / **Pause** / **Stop**, CSV dans `files/`, sorties dans `download/`, `clips/`, `processeds/`.

### Dépannage Linux

| Problème | Solution |
|----------|----------|
| `python3` introuvable | Voir section « Installer Python (CLI) » ci-dessus |
| `python3-venv` manquant | `sudo apt install python3-venv` |
| `ffmpeg` introuvable | Relancer `./install.sh` (télécharge dans `tools/`) ou `sudo apt install ffmpeg` |
| Permission denied | `chmod +x install.sh run.sh` |

---

## Comportement du traitement (Windows & Linux)

1. Liste les CSV dans `files/`
2. Lit chaque ligne (clips à produire)
3. Télécharge les vidéos YouTube (meilleure qualité) dans `download/`  
   - si la vidéo existe déjà → skip  
   - en cas d’erreur **401 / 403** (etc.) → nouvel essai après **3 s**, max **10** essais  
   - aucun clip n’est créé depuis un fichier incomplet (`.part`)
4. Crée un dossier par `videoTitle` dans `clips/`
5. Découpe les clips :  
   `clips/{videoTitle}/{videoTitle}_{start}_{end}.mp4`
6. Si tout s’est bien terminé (sans Stop) : déplace les CSV vers  
   `processeds/YYYY-MM-DD_HH-MM/`

---

## Ce que télécharge `install` dans `tools/`

Les deux OS utilisent le même script : `scripts/fetch_tools.py` (appelé par `install.bat` / `install.sh`).

| Système | Fichiers | Sources (ordre de tentative) |
|---------|----------|------------------------------|
| **Windows** | `ffmpeg.exe`, `ffprobe.exe` | [BtbN win64 GPL](https://github.com/BtbN/FFmpeg-Builds/releases) |
| **Linux** | `ffmpeg`, `ffprobe` | 1) [BtbN linux64/arm64 GPL](https://github.com/BtbN/FFmpeg-Builds/releases) 2) [johnvansickle static](https://johnvansickle.com/ffmpeg/) |

Le script :

- crée `tools/` s’il n’existe pas  
- télécharge, extrait, copie les binaires **dans le dossier du projet**  
- force les droits d’exécution (`chmod +x`) sous Linux  
- teste `ffmpeg -version`  
- échoue clairement si les fichiers sont absents  

Ces fichiers sont **locaux** (après install) et listés dans `.gitignore` (trop lourds pour GitHub).

---

## Fichiers à ne pas confondre

| Fichier | Système |
|---------|---------|
| `install.bat` / `run.bat` | **Windows** |
| `install.sh` / `run.sh` | **Linux** |

---

## Support rapide

| Étape | Windows | Linux |
|-------|---------|-------|
| Python | [Télécharger le Manager MSIX](https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix) | `sudo apt install python3 python3-venv` |
| Install app | Double-clic **`install.bat`** | `./install.sh` |
| Lancer | Double-clic **`run.bat`** → **Start** | `./run.sh` → **Start** |
| CSV | Dossier `files\` | Dossier `files/` |
