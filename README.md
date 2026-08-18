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
WebKitGTK 6.0. Les liens ouverts dans une nouvelle fenêtre restent dans l'application
et le bouton de téléchargement utilise `yt-dlp` pour extraire la vidéo de la page.
L'onglet **Suggestions** utilise un graphe d'affinité SQLite local inspiré de Pinterest :
les visites, téléchargements et applications renforcent les tags correspondants,
puis les résultats sont classés et diversifiés à la demande, sans démon d'analyse.
Des propositions variées issues du Steam Workshop, de MotionBGS, MoeWalls et VSThemes sont fournies par
défaut afin que le fil soit utile avant les premières interactions. Le mélange réserve
une place à chaque site disponible en donnant la priorité au Workshop, puis complète
selon le score et la diversité ; le
faible poids initial laisse rapidement place aux goûts réels.
Deux vidéos populaires de la chaîne YouTube TeshiiSan sont également proposées par
défaut. Leur note publique combine la portée logarithmique des vues à 60 % et le taux
de J’aime à 40 % ; les compteurs utilisés sont affichés directement sur chaque carte.
Les projets Steam de type `Scene` ou `Web` nécessitent Wallpaper Engine/Steam ; les
éléments de type `Video` ne sont importables que si Steam expose un fichier accessible.
Le navigateur intégré active par défaut un bloqueur de publicités : règles réseau pour
les régies connues, masquage des emplacements publicitaires et refus des fenêtres
surgissantes automatiques. Le bouton bouclier permet de désactiver temporairement la
protection lorsqu'un site en a besoin.
Le bouton vidéo de la barre principale importe aussi une URL YouTube en `1080p`,
`1440p` ou `2160p`. `yt-dlp` télécharge et remuxe la meilleure piste disponible en
MP4, l'ajoute à la bibliothèque et la sélectionne pour l'écran choisi. L'utilisateur
doit disposer des droits nécessaires sur la vidéo importée.
MPVpaper Engine privilégie `~/.local/bin/yt-dlp` lorsqu'il existe, car la version
fournie par Debian peut devenir trop ancienne pour les changements fréquents de YouTube.
Le fil utilise des cartes visuelles avec grande miniature mise en cache, titre, source,
note, tags, favori et ouverture directe de la fiche dans **Découvrir**.
La note sur 5 est calibrée selon la pertinence et le volume d'interactions : les
nouveaux éléments restent proches de 3,0, puis visites, téléchargements et favoris
augmentent progressivement la confiance au lieu de produire une note arbitraire.
Installez-la puis ouvrez-la depuis le menu des
applications ou avec le bouton **Fond d'écran** situé en bas de l'écran :

```bash
sudo apt install gir1.2-webkit-6.0 yt-dlp
chmod +x install-mpvpaper-engine.sh
./install-mpvpaper-engine.sh
```

#### Guide d'utilisation

1. Ouvrez **MPVpaper Engine** avec le bouton **Fond d'écran** situé en bas de
   Caelestia ou depuis le menu des applications. Appuyer une seconde fois sur
   le bouton Caelestia ferme la fenêtre.
2. Dans **Bibliothèque**, cliquez sur une miniature, choisissez l'écran dans
   la liste **Écran**, puis réglez le volume, la vitesse, le décodage matériel
   et la pause en plein écran. Cliquez sur **Appliquer le fond** pour valider.
3. Pour attribuer des vidéos différentes, sélectionnez d'abord `eDP-1`,
   appliquez sa vidéo, puis sélectionnez `HDMI-A-1` et appliquez l'autre vidéo.
   N'utilisez **Tous les écrans** que pour afficher volontairement la même vidéo
   partout, car ce choix remplace les affectations individuelles.
4. Le bouton **+** importe une ou plusieurs vidéos déjà présentes sur le disque.
   Le bouton vidéo accepte une adresse YouTube : collez l'URL, choisissez
   `1080p`, `1440p` ou `2160p (4K)`, puis cliquez sur **Télécharger**. La vidéo
   téléchargée rejoint automatiquement la bibliothèque.
5. Dans **Découvrir**, choisissez Steam Workshop, YouTube TeshiiSan, MotionBGS,
   MoeWalls ou VSThemes. Utilisez les flèches pour naviguer, le bouclier pour
   activer ou désactiver le bloqueur de publicités et le bouton de téléchargement
   pour importer la vidéo de la page affichée.
6. Dans **Suggestions**, cliquez sur **Ouvrir** pour consulter une proposition
   dans Découvrir ou sur le cœur pour renforcer ce type de contenu. Le bouton
   d'actualisation recalcule le fil à partir des visites, téléchargements,
   favoris et fonds appliqués.
7. Les cartes YouTube affichent leurs vues et leurs J'aime. Leur note combine
   60 % de portée des vues et 40 % de taux de J'aime ; les autres notes gagnent
   progressivement en confiance selon les interactions locales.
8. **Utiliser pour l'écran de connexion** extrait une image fixe de la vidéo
   sélectionnée. Saisissez le mot de passe administrateur dans le terminal qui
   s'ouvre pour l'installer dans SDDM. **Arrêter le fond vidéo** coupe les fonds
   animés en cours sans supprimer les fichiers de la bibliothèque.
9. Dans **Thèmes**, choisissez le mode clair ou sombre, le thème GTK, les icônes
   et le curseur parmi ceux installés sur la machine. Cliquez sur **Appliquer le
   thème** : le réglage est conservé dans la session et utilisé par les
   applications compatibles. MPVpaper Engine synchronise `gsettings` et les
   configurations GTK 3/4 afin d'éviter qu'un ancien réglage remplace le choix.
   Les nouvelles collections peuvent être installées
   dans `~/.themes` pour GTK et `~/.icons` pour les icônes ou curseurs ; elles
   apparaîtront dans les listes au prochain lancement de MPVpaper Engine.

Les miniatures peuvent prendre quelques secondes à apparaître lors de la première
ouverture. Un téléchargement qui échoue peut provenir d'un site ayant changé son
format ou d'une version trop ancienne de `yt-dlp`; l'application privilégie donc
automatiquement `~/.local/bin/yt-dlp` lorsqu'il est installé.

Le bouton inférieur fonctionne comme une bascule : un premier clic ouvre
MPVpaper Engine et un second clic ferme sa fenêtre.

Les vidéos importées sont conservées dans `~/Pictures/Wallpapers/Live`. Le dernier
fond peut être restauré automatiquement à l'ouverture de la session Hyprland.
Chaque écran peut conserver un fond et des réglages différents : appliquer un fond
à `eDP-1` ne redémarre plus celui de `HDMI-A-1`. Le choix **Tous les écrans** remplace
volontairement les affectations individuelles par un fond commun.
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
