# Arch's Auto Clipping

Application **Windows / Linux** (Python + PySide6) pour télécharger des vidéos YouTube et découper des clips à partir de CSV.

Les binaires lourds (**ffmpeg**, Python Manager…) **ne sont pas** dans ce dépôt : ils sont installés via les liens / scripts d’installation.

## Documentation complète

→ **[DOCUMENTATION.md](DOCUMENTATION.md)**

## Démarrage rapide

### Windows

1. **Python** — télécharger et installer :  
   [python-manager-26.3.msix](https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix)  
   Réponses : **Y**, **Y**, **Y**, **N**
2. Double-clic **`install.bat`** → télécharge aussi `ffmpeg` dans `tools\`
3. Double-clic **`run.bat`** → bouton **Start**

### Linux

```bash
# Python
sudo apt update && sudo apt install -y python3 python3-venv python3-pip

# Application
chmod +x install.sh run.sh
./install.sh    # venv + deps + ffmpeg dans tools/
./run.sh
```
