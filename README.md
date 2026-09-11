# Arch's Auto Clipping

Application **Windows** et **Linux** (Python + PySide6) qui lit des fichiers CSV, télécharge les vidéos YouTube associées, découpe des clips selon les horaires indiqués, puis archive les CSV traités.

Les binaires volumineux (`ffmpeg`, gestionnaire Python, etc.) ne sont **pas** inclus dans le dépôt. Ils sont installés via les liens ci-dessous ou téléchargés automatiquement par les scripts d’installation dans le dossier `tools/`.

---

## Table des matières

1. [Prérequis : navigateur et extension](#prérequis--navigateur-et-extension)
2. [Fonctionnement](#fonctionnement)
3. [Installation sous Windows](#installation-sous-windows)
4. [Installation sous Linux](#installation-sous-linux)
5. [Utilisation](#utilisation)
6. [Format des fichiers CSV](#format-des-fichiers-csv)
7. [Structure du projet](#structure-du-projet)
8. [Outils téléchargés dans tools/](#outils-téléchargés-dans-tools)
9. [Dépannage](#dépannage)

---

## Prérequis : navigateur et extension

Avant d’utiliser **Arch's Auto Clipping**, installez le navigateur et l’extension qui génèrent les fichiers CSV.

### 1. Installer le navigateur Brave

1. Ouvrez le site officiel : [https://brave.com/](https://brave.com/).
2. Téléchargez la version adaptée à votre système (Windows ou Linux).
3. Installez Brave et lancez-le.

### 2. Installer l’extension YouTube Clip Saver

1. Ouvrez le Chrome Web Store : [YouTube Clip Saver](https://chromewebstore.google.com/detail/youtube-clip-saver/ppmgcfhfmkbkfjhjdgdnigfcamapdifp).
2. Cliquez sur **Ajouter à Chrome** (ou l’équivalent proposé par Brave).
3. Confirmez l’installation de l’extension.
4. Utilisez l’extension sur YouTube pour enregistrer des clips ; les exports CSV produits serviront d’entrée pour **Arch's Auto Clipping** (dossier `files/`).

---

## Fonctionnement

1. Liste les fichiers CSV présents dans `files/`.
2. Lit chaque ligne pour identifier les clips à produire.
3. Télécharge les vidéos YouTube (meilleure qualité possible) dans `download/` :
   - Si la vidéo est déjà présente, le téléchargement est ignoré.
   - En cas d’erreur **401**, **403**, SABR, réseau temporaire, nouvel essai après **3 secondes** (maximum **10** essais), en changeant de client YouTube (tv, android, web_embedded…).
   - Au lancement, **yt-dlp** est vérifié sur PyPI et mis à jour automatiquement s’il est trop ancien (cause n°1 des échecs YouTube).
   - Aucun clip n’est créé à partir d’un fichier incomplet (par exemple `.part`).
4. Crée un dossier par `videoTitle` dans `clips/` (sans doublon).
5. Découpe les clips sous la forme :  
   `clips/{videoTitle}/{videoTitle}_{startTime}_{endTime}.mp4`
6. Si le traitement se termine sans arrêt manuel (**Stop**), déplace les CSV vers  
   `processeds/YYYY-MM-DD_HH-MM/`.

---

## Installation sous Windows

### 1. Installer Python

Python n’est pas fourni avec le projet. Téléchargez le **Python Install Manager** officiel :

- Fichier d’installation :  
  [python-manager-26.3.msix](https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix)
- Page de la version :  
  [Python install manager 26.3](https://www.python.org/downloads/release/pymanager-263/)
- Page générale des téléchargements :  
  [python.org/downloads](https://www.python.org/downloads/)

Ensuite :

1. Double-cliquez sur `python-manager-26.3.msix`.
2. Répondez aux questions comme suit :

| Question | Réponse |
|----------|---------|
| Update setting now ? | **Y** |
| Add commands directory to your PATH Now ? | **Y** |
| Install the current latest version of CPython ? | **Y** |
| View Help Online ? | **N** |

3. Fermez puis rouvrez l’Explorateur de fichiers (ou le terminal) pour que le `PATH` soit pris en compte.

### 2. Installer l’application

1. Double-cliquez sur **`install.bat`**  
   (ne pas utiliser `install.sh`, réservé à Linux).
2. Une fenêtre de terminal s’ouvre. Le script :
   - Crée l’environnement virtuel `.venv`.
   - Installe les dépendances Python (`PySide6`, `yt-dlp`).
   - Télécharge dans `tools\` : `ffmpeg.exe` et `ffprobe.exe` (s’ils sont absents).
3. Appuyez sur une touche lorsque c’est demandé pour terminer.
4. Le terminal se ferme à la fin de l’installation.

### 3. Lancer l’application

1. Double-cliquez sur **`run.bat`**  
   (ne pas utiliser `run.sh`, réservé à Linux).
2. La fenêtre **Arch's Auto Clipping** s’affiche. Les logs indiquent si les librairies sont à jour (`yt-dlp`, `PySide6`).
3. Cliquez sur **Start** pour démarrer le traitement.

---

## Installation sous Linux

### 1. Installer Python

**Debian / Ubuntu :**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

**Fedora :**

```bash
sudo dnf install -y python3 python3-pip
```

**Arch Linux :**

```bash
sudo pacman -S python
```

La version de Python doit être **3.10** ou supérieure.

### 2. Installer l’application

```bash
cd /chemin/vers/le/projet
chmod +x install.sh run.sh
./install.sh
```

Le script :

- Crée l’environnement virtuel `.venv`.
- Installe les dépendances Python (`PySide6`, `yt-dlp`).
- Crée les dossiers `files/`, `download/`, `clips/`, `processeds/` et `tools/`.
- Télécharge dans `tools/` : `ffmpeg` et `ffprobe` (s’ils sont absents).

### 3. Lancer l’application

```bash
./run.sh
```

Puis cliquez sur **Start** dans la fenêtre **Arch's Auto Clipping**.

Au lancement, l’application interroge PyPI : `yt-dlp` est mis à jour tout seul si une version plus récente existe. `PySide6` est seulement signalé (relancez `./install.sh` pour l’appliquer).

---

## Utilisation

### Interface

| Bouton | Action |
|--------|--------|
| **Start** | Démarre le traitement des CSV placés dans `files/` |
| **Pause** / **Resume** | Met le traitement en pause ou le reprend |
| **Stop** | Arrête le traitement en cours (les CSV ne sont pas archivés) |

### Dossiers

| Dossier | Rôle |
|---------|------|
| `files/` | Fichiers CSV à traiter |
| `download/` | Vidéos YouTube téléchargées en entier |
| `clips/` | Clips découpés (un sous-dossier par vidéo) |
| `processeds/` | CSV déjà traités, classés par date et heure |
| `tools/` | Binaires locaux (`ffmpeg`, etc.), non versionnés sur GitHub |

### Fichiers d’installation et de lancement

| Fichier | Système |
|---------|---------|
| `install.bat` / `run.bat` | Windows |
| `install.sh` / `run.sh` | Linux |

---

## Format des fichiers CSV

Colonnes **obligatoires** :

| Colonne | Description |
|---------|-------------|
| `videoTitle` | Titre de la vidéo (nom du fichier téléchargé et du dossier de clips) |
| `videoUrl` | URL YouTube |
| `startTime` | Début du clip (en secondes) |
| `endTime` | Fin du clip (en secondes) |

Colonne **optionnelle** utile : `videoId` (déduplication des téléchargements).

Exemple :

```csv
videoTitle,videoId,startTime,endTime,duration,direction,note,tags,videoUrl,savedAt
Exemple de titre,yY6Bd3jAXyM,2,18,16,manual,,,https://www.youtube.com/watch?v=yY6Bd3jAXyM,0
```

Placez vos fichiers CSV dans le dossier **`files/`** avant de cliquer sur **Start**.

---

## Structure du projet

```
├── install.bat / run.bat      # Windows
├── install.sh / run.sh        # Linux
├── main.py
├── requirements.txt
├── README.md
├── scripts/                   # Code de l'application
├── files/                     # CSV d'entrée
├── download/                  # Vidéos complètes
├── clips/                     # Clips par vidéo
├── processeds/                # Archives CSV
└── tools/                     # Binaires téléchargés localement
```

---

## Outils téléchargés dans tools/

Les scripts `install.bat` et `install.sh` appellent `scripts/fetch_tools.py`, qui détecte le système d’exploitation et installe les binaires manquants.

| Système | Fichiers | Sources |
|---------|----------|---------|
| Windows | `ffmpeg.exe`, `ffprobe.exe` | [BtbN FFmpeg-Builds (win64 GPL)](https://github.com/BtbN/FFmpeg-Builds/releases) |
| Linux | `ffmpeg`, `ffprobe` | [BtbN FFmpeg-Builds (linux64 / arm64)](https://github.com/BtbN/FFmpeg-Builds/releases), puis en secours [johnvansickle.com/ffmpeg](https://johnvansickle.com/ffmpeg/) |

Le script :

- Crée le dossier `tools/` s’il n’existe pas.
- Télécharge, extrait et copie les binaires dans le projet.
- Applique les droits d’exécution sous Linux (`chmod +x`).
- Vérifie le fonctionnement avec `ffmpeg -version`.

Ces fichiers restent locaux et sont exclus de Git (voir `.gitignore`).

Pour ne retélécharger que les outils :

```bash
# Linux
python3 scripts/fetch_tools.py

# Windows (avec le venv déjà créé)
.venv\Scripts\python.exe scripts\fetch_tools.py
```

---

## Dépannage

### Le téléchargement YouTube échoue (403, SABR, « sign in »)

YouTube change souvent ses protections. L’application :

1. Met **yt-dlp** à jour au lancement.
2. Retente jusqu’à 10 fois en changeant de client (tv, android, web_embedded…).
3. Peut lire un fichier **`cookies.txt`** (format Netscape) placé à la racine du projet.

Pour exporter les cookies depuis Brave :

1. Installez une extension du type **Get cookies.txt LOCALLY**.
2. Ouvrez YouTube dans Brave, exportez `cookies.txt`.
3. Copiez le fichier à la racine du projet (à côté de `main.py`).
4. Relancez l’application puis **Start**.

Ne commitez jamais `cookies.txt` (il contient votre session).

Pour la meilleure qualité (1080p+), installez **Node.js** (LTS) ou **Deno** : yt-dlp s’en sert pour résoudre les défis JavaScript de YouTube. Sans ça, l’application se rabat sur le client Android (souvent 360p, mais ça télécharge).

### Windows

| Problème | Solution |
|----------|----------|
| Python introuvable | Installer le [Python Install Manager](https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix), puis rouvrir le terminal |
| `tools\ffmpeg.exe` absent | Relancer `install.bat` ou exécuter `scripts\fetch_tools.py` |
| Erreur au lancement de `run.bat` | Vérifier que `install.bat` a bien terminé (présence de `.venv`) |
| Téléchargement YouTube en échec | Laisser l’app mettre à jour yt-dlp au lancement, ou placer un `cookies.txt` à la racine |

### Linux

| Problème | Solution |
|----------|----------|
| `python3` introuvable | Installer Python (voir [Installation sous Linux](#installation-sous-linux)) |
| Module `venv` manquant | `sudo apt install python3-venv` |
| `ffmpeg` introuvable | Relancer `./install.sh` ou `python3 scripts/fetch_tools.py` |
| Permission denied | `chmod +x install.sh run.sh tools/ffmpeg tools/ffprobe` |
| Téléchargement YouTube en échec | Même procédure que Windows (`cookies.txt` + mise à jour yt-dlp) |

---

## Récapitulatif

| Étape | Windows | Linux |
|-------|---------|-------|
| Python | [python-manager-26.3.msix](https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix) | `sudo apt install python3 python3-venv python3-pip` |
| Installation | Double-clic sur `install.bat` | `./install.sh` |
| Lancement | Double-clic sur `run.bat`, puis **Start** | `./run.sh`, puis **Start** |
| Données | Placer les CSV dans `files\` | Placer les CSV dans `files/` |
