# Debian Hyprland Custom

## v2 — Debian Immersive avec Caelestia

La v2 remplace la barre Waybar par [Caelestia Shell](https://github.com/caelestia-dots/shell),
une interface Quickshell fluide avec lanceur, tableau de bord, visualiseur audio,
fond dynamique et panneaux translucides. La configuration v1 « Debian Glass »
reste disponible et n'est pas supprimée.

### Prérequis v2

- une session Hyprland fonctionnelle ;
- `caelestia-cli` ;
- la version **git** de Quickshell (`qs`) ;
- les dépendances Caelestia (`ddcutil`, `brightnessctl`, `libcava`,
  NetworkManager, `lm-sensors`, Fish, Aubio, PipeWire, Qt 6, polices Material
  Symbols et Caskaydia Cove Nerd Font).

Caelestia est principalement empaqueté pour Arch et Nix. Sous Debian, compilez
Quickshell git et Caelestia selon leurs documentations officielles ;
`install-v2.sh` s'arrête proprement si les deux commandes indispensables ne sont
pas disponibles.

```bash
chmod +x install-v2.sh
./install-v2.sh
```

L'installateur sauvegarde les fichiers concernés dans
`~/.config/debian-immersive-v2-backup-*`, pose le profil dans
`~/.config/caelestia/shell.json` et ajoute un unique `source` à Hyprland.

Raccourcis principaux : `Super+Espace` lanceur, `Super+D` tableau de bord,
`Super+N` panneau latéral, `Super+M` utilitaires, `Super+L` verrouillage et
`Ctrl+Alt+Suppr` menu de session. Le fond d'écran est lu depuis
`~/Pictures/Wallpapers`.

### Écran externe

Hyprland détecte automatiquement les écrans branchés, mais leur disposition
doit être enregistrée une première fois. Lancez `nwg-displays`, placez l'écran
externe à gauche ou à droite de l'écran intégré, choisissez sa résolution et sa
fréquence, puis utilisez **Apply** et **Save**. L'outil écrit une configuration
précise dans `~/.config/hypr/monitors.conf` et remplace les règles génériques qui
peuvent sélectionner un mode imprévisible.

Pour diagnostiquer un écran non détecté, utilisez `hyprctl monitors all`. Sur un
portable, l'écran interne est généralement nommé `eDP-1` et une sortie HDMI
`HDMI-A-1`.

### Verrouillage sous Debian

Le raccourci de verrouillage privilégie `/usr/bin/hyprlock`, fourni par le paquet
Debian et intégré à PAM. Cela évite qu'une compilation installée dans
`/usr/local/bin` masque la version du système et refuse un mot de passe valide.

### Profil d'affichage OLED

Le profil v2 applique au démarrage une température neutre de 6500 K et un gamma
prononcé de 70 % avec `hyprsunset`. Le raccourci `Super+Shift+O` bascule entre ce
rendu plus sombre et les couleurs neutres. Les valeurs peuvent être ajustées avec
`CAELESTIA_DISPLAY_GAMMA` et `CAELESTIA_DISPLAY_TEMPERATURE`.

### MPVpaper Engine

Une interface GTK 4 permet de gérer les fonds d'écran vidéo avec miniatures,
recherche, import, choix du moniteur, volume, vitesse, décodage matériel et pause
automatique en plein écran. L'onglet **Découvrir** intègre MotionBGS, MoeWalls et
VSThemes avec navigation et téléchargement direct dans la bibliothèque, grâce à
WebKitGTK 6.0. Installez-la puis ouvrez-la depuis le menu des
applications ou avec le bouton **Fond d'écran** situé en bas de l'écran :

```bash
sudo apt install gir1.2-webkit-6.0
chmod +x install-mpvpaper-engine.sh
./install-mpvpaper-engine.sh
```

Le bouton inférieur fonctionne comme une bascule : un premier clic ouvre
MPVpaper Engine et un second clic ferme sa fenêtre.

Les vidéos importées sont conservées dans `~/Pictures/Wallpapers/Live`. Le dernier
fond peut être restauré automatiquement à l'ouverture de la session Hyprland.
Le raccourci `Super+W` reste réservé au sélecteur standard de fonds d'écran fixes.
Le bouton **Utiliser pour l'écran de connexion** extrait une image de la vidéo
sélectionnée, ouvre un terminal d'autorisation et l'installe dans le thème SDDM
après saisie du mot de passe administrateur.
SDDM ne prenant pas en charge `mpvpaper`, l'écran de connexion reste une image fixe.

## v1 — Debian Glass / Waybar

Une surcouche réutilisable pour les dotfiles
[KooL Hyprland](https://github.com/JaKooLit/Hyprland-Dots), pensée pour Debian.

## Fonctionnalités

- barre Waybar « Debian Glass » adaptative ;
- bureaux avec icônes des applications ouvertes ;
- mini-lecteur MPRIS inspiré de Spotify ;
- visualiseur audio Cava ;
- commandes précédent, lecture/pause et suivant ;
- panneau multimédia GTK avec volume et sortie audio ;
- couleurs pilotées par `panel-colors.css`.

## Installation

Cette configuration suppose une session Hyprland et les dotfiles KooL déjà
installés. Elle nécessite notamment `waybar`, `playerctl`, `cava`, `jq`,
`python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`, `wireplumber`, `pulseaudio-utils`,
`rofi`, `kitty` et `btop`.

```bash
git clone https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git
cd Debian-Hyprland-Custom
./install.sh
```

L’installateur sauvegarde la configuration Waybar active avant de poser les
fichiers. Déconnectez-vous puis reconnectez-vous si Waybar ne se recharge pas.

## Commandes du lecteur

- clic sur le titre : ouvre le panneau multimédia ;
- clic du milieu sur le titre : lecture/pause ;
- clic droit sur le titre : titre suivant ;
- boutons dédiés : précédent, lecture/pause et suivant.

## Crédits

- Projet et dotfiles originaux : [@JaKooLit](https://github.com/JaKooLit)
- Personnalisation Debian : [@kebemouhamet08-gif](https://github.com/kebemouhamet08-gif)
- Dédicace aux communautés Debian, Hyprland et Caelestia, dont le travail rend
  cette configuration possible.

Ce dépôt redistribue des éléments adaptés du projet original sous GNU GPL v3.
Consultez [LICENSE.md](LICENSE.md).
