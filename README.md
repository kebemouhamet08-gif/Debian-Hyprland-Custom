# Debian Hyprland Custom

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

Ce dépôt redistribue des éléments adaptés du projet original sous GNU GPL v3.
Consultez [LICENSE.md](LICENSE.md).
