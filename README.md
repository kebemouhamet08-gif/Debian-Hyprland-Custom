# Deblestia — Debian × Caelestia

Ce dépôt regroupe plusieurs composants indépendants. Ils sont présentés par leur
nom dans ce guide : **Deblestia Bar**, **Deblestia Nova**, **Deblestia Nova Lite**, **Deblestia Shell**,
**MPVpaper Engine**, **PeriphX** et **MirrorBridge**. Les commandes historiques restent disponibles
comme alias techniques afin de préserver les installations existantes.

## Installation guidée

Cette méthode télécharge le dépôt, affiche les composants par leur vrai nom,
vérifie les prérequis lorsque l'installateur le permet, puis demande confirmation
avant l'installation. Copiez-collez le bloc complet :

```bash
git clone --depth 1 https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git
cd Debian-Hyprland-Custom
./installation-guidee.sh
```

Le menu peut aussi être contourné en indiquant directement le composant, par
exemple `./installation-guidee.sh periphx`. L'installation reste locale au compte
utilisateur, sauf lorsqu'une dépendance système doit être installée séparément.

## Télécharger et installer un seul composant

Chaque bloc ci-dessous crée son propre dossier et utilise le clonage partiel de
Git. Il télécharge le script racine et uniquement la partie de `config/` nécessaire.
Exécutez un bloc à la fois depuis le dossier dans lequel vous souhaitez conserver
les sources.

### Deblestia Bar

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git deblestia-bar
cd deblestia-bar
git sparse-checkout set config/waybar config/hypr
./install-deblestia-bar.sh
```

### Deblestia Nova

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git deblestia-nova
cd deblestia-nova
git sparse-checkout set config/nova-shell config/hypr
./install-deblestia-nova.sh check
./install-deblestia-nova.sh install
./install-deblestia-nova.sh launch
```

### Deblestia Nova Lite

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git deblestia-nova-lite
cd deblestia-nova-lite
git sparse-checkout set config/waybar config/hypr
./install-deblestia-nova-lite.sh
```

### Deblestia Shell

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git deblestia-shell
cd deblestia-shell
git sparse-checkout set config/caelestia config/hypr config/v2
./install-deblestia-shell.sh check
./install-deblestia-shell.sh install
```

### MPVpaper Engine

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git mpvpaper-engine
cd mpvpaper-engine
git sparse-checkout set config/mpvpaper-engine
./install-mpvpaper-engine.sh check
./install-mpvpaper-engine.sh install
```

### PeriphX

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git periphx
cd periphx
git sparse-checkout set config/v3
./install-periphx.sh check
./install-periphx.sh install
./install-periphx.sh launch
```

### MirrorBridge

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git mirrorbridge
cd mirrorbridge
git sparse-checkout set config/mirrorbridge
./install-mirrorbridge.sh check
./install-mirrorbridge.sh install
./install-mirrorbridge.sh launch
```

## MirrorBridge — miroir Android et iPhone

MirrorBridge fournit une interface GTK4 pour détecter les téléphones Android avec
ADB, lancer leur recopie et leur contrôle avec scrcpy, ou démarrer un récepteur
AirPlay pour iPhone avec UxPlay. La version 0.1 ouvre encore le flux dans la
fenêtre du moteur externe.

Sous Debian 13 « Trixie », installez d'abord les dépendances de compilation,
ADB, UxPlay et Avahi :

```bash
sudo apt update
sudo apt install cargo pkg-config libgtk-4-dev adb uxplay avahi-daemon
```

Le paquet `scrcpy` fourni par APT est signalé comme obsolète par son projet.
Installez plutôt la construction statique de la
[dernière version officielle](https://github.com/Genymobile/scrcpy/releases/latest),
ou suivez la procédure officielle de
[compilation sous Linux](https://github.com/Genymobile/scrcpy/blob/master/doc/linux.md).
UxPlay peut être installé avec APT sous Debian ; son développement actif se
trouve dans le dépôt [FDH2/UxPlay](https://github.com/FDH2/UxPlay).

```bash
./install-mirrorbridge.sh check
./install-mirrorbridge.sh install
./install-mirrorbridge.sh launch
```

Sur Android, activez le débogage USB et acceptez l’autorisation affichée par le
téléphone. Sur iPhone, ouvrez **Centre de contrôle → Recopie de l’écran**, puis
sélectionnez **MirrorBridge**. Les commandes `adb`, `scrcpy`, `uxplay` et le
service `avahi-daemon` fournissent les backends système nécessaires.

## Deblestia Shell — environnement Caelestia

Dans son propre profil, Deblestia Shell utilise [Caelestia Shell](https://github.com/caelestia-dots/shell)
à la place de Waybar,
une interface Quickshell fluide avec lanceur, tableau de bord, visualiseur audio,
fond dynamique et panneaux translucides. Elle est indépendante de
Deblestia Bar : aucun composant ne remplace l'autre et l'utilisateur installe
uniquement les expériences qu'il souhaite conserver.

Deblestia Shell adopte aussi progressivement certains concepts de
[HyDE](https://github.com/HyDE-Project/HyDE) : installation modulaire, thèmes
interchangeables, couleurs dynamiques, sélecteurs et profils. Leur adaptation à
Debian est découpée en étapes vérifiables dans la
[feuille de route Deblestia Shell](docs/V2-ROADMAP.md) ; l'installateur Arch de HyDE n'est pas
utilisé directement.

Le catalogue des thèmes officiels HyDE suivis par Deblestia Shell se trouve dans
`config/v2/themes.tsv`. Il référence les branches de
[hyde-themes](https://github.com/HyDE-Project/hyde-themes), sans importer leur
installateur Arch. Chaque thème devra être adapté au format Deblestia Shell avant son
activation : Hyprland, GTK, Caelestia/Waybar, icônes, polices et fonds restent
isolés dans le profil Deblestia Shell et sont restaurables.

### Prérequis de Deblestia Shell

- une session Hyprland fonctionnelle ;
- `caelestia-cli` ;
- la version **git** de Quickshell (`qs`) ;
- les dépendances Caelestia (`ddcutil`, `brightnessctl`, `libcava`,
  NetworkManager, `lm-sensors`, Fish, Aubio, PipeWire, Qt 6, polices Material
  Symbols et Caskaydia Cove Nerd Font).

Caelestia est principalement empaqueté pour Arch et Nix. Sous Debian, compilez
Quickshell git et Caelestia selon leurs documentations officielles ;
`install-deblestia-shell.sh` s'arrête proprement si les deux commandes indispensables ne sont
pas disponibles.

```bash
./install-deblestia-shell.sh check
./install-deblestia-shell.sh install
```

L'installateur Deblestia Shell est indépendant et propose aussi `status`,
`restore` et le mode `--dry-run`. Sans argument, il reste équivalent à `install`.

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

Le raccourci `Super+L` ouvre en priorité le verrouillage natif de Caelestia.
Si son IPC ou sa compatibilité PAM ne sont pas disponibles, il utilise
`/usr/bin/hyprlock`, fourni par Debian, comme solution de repli sécurisée.

L'écran verrouillé natif de Caelestia utilise également `pam_faillock`. Sur
Debian, son compteur utilisateur peut être absent et chaque tentative est alors
affichée à tort comme un mot de passe incorrect. La commande suivante installe
le compteur persistant attendu, sans modifier le mot de passe :

```bash
./install-deblestia-shell.sh pam-fix
```

La commande demande les droits administrateur uniquement pour créer la règle
`/etc/tmpfiles.d/deblestia-caelestia-faillock.conf`. Elle est réappliquée
automatiquement à chaque démarrage.

### Profil d'affichage OLED

Le profil Deblestia Shell applique au démarrage une température neutre de 6500 K et un gamma
prononcé de 70 % avec `hyprsunset`. Le raccourci `Super+Shift+O` bascule entre ce
rendu plus sombre et les couleurs neutres. Les valeurs peuvent être ajustées avec
`CAELESTIA_DISPLAY_GAMMA` et `CAELESTIA_DISPLAY_TEMPERATURE`.

## MPVpaper Engine — fonds d'écran vidéo

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
L'onglet **Couleurs**, également accessible depuis **PeriphX → Affichage**, règle
la luminosité, le contraste, le gamma, la saturation, la teinte, la température
et la balance rouge/vert/bleu du fond vidéo. Chaque écran possède son profil et
l'aperçu passe par le socket IPC de mpv sans redémarrer la vidéo. Les curseurs ne
modifient pas la configuration tant que le bouton **Appliquer** n'est pas utilisé ;
**Annuler** restaure immédiatement les valeurs enregistrées.
Installez-la puis ouvrez-la depuis le menu des
applications ou avec le bouton **Fond d'écran** situé en bas de l'écran :

```bash
sudo apt update
sudo apt install ffmpeg ffmpegthumbnailer python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-webkit-6.0 yt-dlp
./install-mpvpaper-engine.sh check
./install-mpvpaper-engine.sh install
```

La commande `mpvpaper` doit également être installée. Si votre version de Debian
ne la fournit pas, suivez la procédure de compilation du
[projet mpvpaper](https://github.com/GhostNaN/mpvpaper) avec Meson, Ninja et
`libmpv-dev`, puis relancez la commande `check` ci-dessus.

### Guide d'utilisation

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
4. Dans **Couleurs**, sélectionnez l'écran, essayez un profil rapide ou déplacez
   les curseurs. Cliquez sur **Appliquer** pour conserver le rendu, ou sur
   **Annuler** pour revenir au profil précédent.
5. Le bouton **+** importe une ou plusieurs vidéos déjà présentes sur le disque.
   Le bouton vidéo accepte une adresse YouTube : collez l'URL, choisissez
   `1080p`, `1440p` ou `2160p (4K)`, puis cliquez sur **Télécharger**. La vidéo
   téléchargée rejoint automatiquement la bibliothèque.
6. Dans **Découvrir**, choisissez Steam Workshop, YouTube TeshiiSan, MotionBGS,
   MoeWalls ou VSThemes. Utilisez les flèches pour naviguer, le bouclier pour
   activer ou désactiver le bloqueur de publicités et le bouton de téléchargement
   pour importer la vidéo de la page affichée.
7. Dans **Suggestions**, cliquez sur **Ouvrir** pour consulter une proposition
   dans Découvrir ou sur le cœur pour renforcer ce type de contenu. Le bouton
   d'actualisation recalcule le fil à partir des visites, téléchargements,
   favoris et fonds appliqués.
8. Les cartes YouTube affichent leurs vues et leurs J'aime. Leur note combine
   60 % de portée des vues et 40 % de taux de J'aime ; les autres notes gagnent
   progressivement en confiance selon les interactions locales.
9. **Utiliser pour l'écran de connexion** extrait une image fixe de la vidéo
   sélectionnée. Saisissez le mot de passe administrateur dans le terminal qui
   s'ouvre pour l'installer dans SDDM. **Arrêter le fond vidéo** coupe les fonds
   animés en cours sans supprimer les fichiers de la bibliothèque.
10. Dans **Thèmes**, choisissez le mode clair ou sombre, le thème GTK, les icônes
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
Les suggestions fonctionnent comme un flux renouvelé : les cartes sont tirées au
hasard selon leur note et vos préférences, et les résultats venant d'être affichés
sont exclus avant le tirage. SQLite mémorise durablement leur empreinte : une image
ou une vidéo déjà proposée ne réapparaît pas après la fermeture ou le redémarrage.
Chaque contenu inédit conserve néanmoins une probabilité minimale afin de favoriser
la découverte au lieu de rendre les faibles scores invisibles.
Le fil charge ensuite de nouveaux lots lorsque le défilement atteint le bas. Après
l'ouverture ou la mise en favori d'une carte, celle-ci devient la graine du flux :
chaque tag partagé multiplie par cinq la probabilité contextuelle, tout en laissant
une chance aux styles différents pour permettre une dérive progressive.
Enfin, 15 % de chaque lot sont réservés en priorité à des tags encore absents du
profil : cette exploration forcée limite la bulle de filtres et permet aux goûts
d'évoluer.
Le défilement n'a aucun plafond logiciel. Lorsqu'il atteint les contenus connus, le
moteur poursuit les catalogues puis réessaie automatiquement avec un délai progressif
si les sources sont temporairement inaccessibles. Il attend un contenu réellement
nouveau au lieu de recycler une ancienne carte. Les miniatures téléchargées se
mettent à jour sur place sans vider le flux ni remonter la page.
Dans l'onglet **Suggestions**, le mode Pinterest précharge la suite à 360 pixels de
la fin et continue jusqu'à remplir la fenêtre. Le nombre de cartes n'est pas fixe :
il est calculé selon la largeur, la hauteur visible et le nombre de colonnes. Chaque
lot est produit au moment du chargement à partir du profil, de la graine contextuelle,
du cooldown et de l'exploration ; il ne s'agit pas d'une liste préparée à l'avance.
La carte située au centre de la zone visible devient automatiquement la nouvelle
graine après 120 ms de stabilité. Le prochain lot suit donc naturellement le contenu
réellement regardé, même sans clic, tandis qu'un clic ou un favori reste un signal
plus fort pour le profil persistant.
Quand le flux manque de nouveautés, le moteur interroge immédiatement les catalogues
configurés et ajoute les fiches inédites à SQLite. Un timer utilisateur poursuit aussi
l'exploration à faible priorité toutes les cinq minutes, à l'ouverture de session et
après la fermeture de MPVpaper Engine. Il n'existe ni cible totale ni nombre maximal
de suggestions : chaque petite passe reprend la frontière persistante là où la
précédente s'est arrêtée.
Ces passes ne téléchargent pas les vidéos.
Les URL sont en plus dédupliquées par contenu : identifiant vidéo YouTube, identifiant
Steam ou signature normalisée du titre. Deux pages pointant vers la même vidéo ou la
même image ne peuvent donc pas occuper deux cartes du flux. Cette exclusion persiste
entre toutes les sessions.

Le bouton inférieur fonctionne comme une bascule : un premier clic ouvre
MPVpaper Engine et un second clic ferme sa fenêtre.

Les vidéos importées sont conservées dans `~/Pictures/Wallpapers/Live`. Le dernier
fond peut être restauré automatiquement à l'ouverture de la session Hyprland.
Chaque écran peut conserver un fond et des réglages différents : appliquer un fond
à `eDP-1` ne redémarre plus celui de `HDMI-A-1`. Le choix **Tous les écrans** remplace
volontairement les affectations individuelles par un fond commun.
Sur toutes les configurations Waybar fournies, un clic droit sur le module de fond
d'écran choisit une vidéo aléatoire en conservant les réglages MPVpaper actifs.
Le raccourci `Super+W` reste réservé au sélecteur standard de fonds d'écran fixes.
Le bouton **Utiliser pour l'écran de connexion** extrait une image de la vidéo
sélectionnée, ouvre un terminal d'autorisation et l'installe dans le thème SDDM
après saisie du mot de passe administrateur.
SDDM ne prenant pas en charge `mpvpaper`, l'écran de connexion reste une image fixe.

## PeriphX — centre de contrôle matériel

PeriphX est préparé comme un composant indépendant. Son manifeste se
trouve dans `config/v3/components.tsv` et sa feuille de route dans
`docs/V3-ROADMAP.md`. Il ne modifie ni Deblestia Bar ni Deblestia Shell.

Installez le centre de contrôle matériel avec :

```bash
./install-periphx.sh check
./install-periphx.sh install
./install-periphx.sh launch
```

Après avoir ajouté `~/.local/bin` au `PATH`, lancez PeriphX ainsi :

```bash
export PATH="$HOME/.local/bin:$PATH"
periphx
```

La CLI expose l'inventaire et l'inspection détaillée sans écrire vers le matériel :

```bash
periphx-cli list
periphx-cli inspect DEVICE_ID
periphx-cli interfaces DEVICE_ID
periphx-cli capture DEVICE_ID --duration-ms 1000
```

La capture n'ouvre que les nœuds `hidraw` rattachés au périphérique sélectionné,
avec `O_RDONLY`, une durée maximale de 30 secondes et au plus 1 000 reports. Si
les permissions Linux refusent la lecture, PeriphX renvoie une erreur explicite
et ne modifie jamais les permissions du périphérique automatiquement.

Des manifests de pilotes custom peuvent être validés, installés et mis à jour en
lecture seule. Le format et ses garanties de sécurité sont décrits dans
[`docs/PERIPHX-CUSTOM-DRIVERS.md`](docs/PERIPHX-CUSTOM-DRIVERS.md).

Il affiche les périphériques USB/HID, Bluetooth, claviers, souris, écrans et manettes détectés
par Debian. Les capacités DDC/CI, OpenRGB, evdev/uinput et les profils sont
indiqués séparément ; un périphérique propriétaire ne sera pas piloté sans backend
compatible ni permission explicite.

L'interface graphique de PeriphX nécessite les bindings Python de GTK 4 et de
Libadwaita. `cargo` est recommandé pour compiler le démon `pericored` :

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 cargo
```

`pericored` agrège les nœuds `event`, `mouse` et `hidraw` par périphérique physique.
Son pilote HID générique décode chaque interface et son descripteur, calcule une
empreinte SHA-256 et reste strictement en lecture seule tant qu'aucun pilote validé
n'est associé au VID/PID concerné.

## Deblestia Nova — shell Quickshell complet

Deblestia Nova est désormais l'expérience complète inspirée de
[end4-pC](https://github.com/pctrade/end4-pC) : barre Material Expressive,
panneaux latéraux, lanceur/recherche, aperçu des bureaux, notifications, réglages,
dock, widgets de bureau, OSD, sélecteur de fond d'écran et menu de session. Le code
amont GPLv3 est téléchargé au moment de l'installation puis adapté avec un preset
Debian et une correction de compatibilité Qt 6.8, sans lancer l'installateur
Arch/Nix du projet d'origine.

Le profil Debian remplace les commandes `pacman` et KDE par `apt`, `nmtui`,
`blueman-manager`, `btop` et `pavucontrol`. Il conserve les démons de notifications
et trays existants tant que l'utilisateur ne choisit pas de les arrêter. Le
verrouillage `Super+L` utilise Hyprlock installé par Debian afin d'éviter les
incompatibilités PAM déjà rencontrées.

L'installation désactive l'ancien `caelestia-v2.conf` et ajoute le profil
`[Deblestia] Nova` au sélecteur des barres. Ce profil active exclusivement le
shell Quickshell complet : barre supérieure avec lecteur, horloge analogique sur
le bureau et dock/menu d'applications permanent en bas. Choisir une autre Waybar
arrête ensemble ces trois éléments Nova avant de lancer la barre sélectionnée ;
`no panel` arrête les deux systèmes. La restauration remet la configuration
Hyprland sauvegardée.

### Installation copier-coller sur Debian

Quickshell (`qs`) doit déjà être fonctionnel. Les paquets ci-dessous couvrent les
fonctions principales ; certains outils peuvent ne pas exister dans toutes les
versions de Debian et restent optionnels :

```bash
sudo apt update
sudo apt install git python3 jq curl fish cava brightnessctl ddcutil \
  network-manager network-manager-gnome blueman wl-clipboard imagemagick \
  swappy slurp wf-recorder tesseract-ocr playerctl upower qalc \
  pavucontrol kitty btop libnotify-bin

git clone --depth 1 https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git
cd Debian-Hyprland-Custom
./install-deblestia-nova.sh check
./install-deblestia-nova.sh install
./install-deblestia-nova.sh launch
```

Les commandes de maintenance sont :

```bash
./install-deblestia-nova.sh status
./install-deblestia-nova.sh update
./install-deblestia-nova.sh restore
```

`install` et `update` créent une sauvegarde dans
`~/.config/deblestia-nova-backups/`. `restore` remet la dernière sauvegarde et
conserve à son tour l'état remplacé. Les réglages de Nova restent dans
`~/.config/illogical-impulse/config.json`.

Raccourcis principaux : `Super+Espace` recherche, `Super+Échap` réglages,
`Super+N` panneau droit, `Super+Maj+N` panneau gauche, `Super+Maj+W` fonds
d'écran, `Super+Maj+B` barre et `Ctrl+Alt+Suppr` session.

## Deblestia Nova Lite — Waybar en îlots

Deblestia Nova Lite est une barre Waybar horizontale qui reprend l'organisation
de la barre Nova/Quickshell. Elle utilise une palette sombre et neutre, sans ombre
colorée, rail latéral ni barre inférieure. Le profil apparaît sous le nom
`[Deblestia] Nova Lite`. Comme toute autre Waybar, sa sélection arrête complètement
le shell Nova afin d'éviter les doubles barres et les réservations invisibles.

Le profil `[CUSTOM] Debian Glass` utilise lui aussi une disposition supérieure
complète et conserve ses fonctions historiques : lecteur, applications, bureaux,
restauration des fenêtres réduites, météo, état système et contrôles de session.
Son lecteur central adopte une capsule inspirée de Spotify avec visualisation
audio CAVA, métadonnées MPRIS et commandes précédent, lecture/pause et suivant.

Nova Lite est le profil Waybar sélectionné par défaut par `install.sh`. Deblestia Bar
reste disponible avec `install-deblestia-bar.sh` ou avec le sélecteur de profil.

Fonctions supplémentaires de Nova Lite :

- fenêtre active, lanceurs rapides et bureaux avec icônes d'applications ;
- lecteur MPRIS complet et panneau multimédia GTK ;
- tiroirs extensibles pour CPU, mémoire, température, disque et outils ;
- volume et luminosité réglables à la molette ;
- état réseau, Bluetooth, batterie et profil d'énergie ;
- indicateurs de confidentialité pour le microphone, la caméra et le partage ;
- historique du presse-papiers, capture de zone et pipette couleur ;
- palettes Rose, Tokyo, Nord, Gruvbox, Mono et couleurs du fond d'écran ;
- notifications, veille, mises à jour APT, tray et panneau d'alimentation ;
- centre Focus inspiré de l'approche modulaire d'end4-pC : Pomodoro persistant,
  pauses courtes/longues et notes locales ;
- accès à MPVpaper Engine depuis le tiroir d'outils.

Les commandes enrichies utilisent, lorsqu'elles sont installées, `brightnessctl`,
`cliphist`, `grim`, `hyprpicker`, `powerprofilesctl`, `slurp`, `swaync-client` et
`wl-copy`. Leur absence désactive uniquement le bouton concerné.

Le bouton palette du tiroir d'outils applique les couleurs sans redémarrer la
session. La commande équivalente accepte `rose`, `tokyo`, `nord`, `gruvbox`,
`mono` ou `wallpaper` :

```bash
~/.config/waybar/deblestia-theme.sh tokyo
```

```bash
./install-deblestia-nova-lite.sh check
./install-deblestia-nova-lite.sh
```

Après installation, un clic droit sur le logo Debian permet de basculer entre
Nova Lite et Bar. La même action est disponible en ligne de commande :

```bash
~/.config/waybar/deblestia-waybar-switch.sh nova
~/.config/waybar/deblestia-waybar-switch.sh bar
```

## Deblestia Bar — barre Waybar verticale

Une surcouche réutilisable pour les dotfiles
[KooL Hyprland](https://github.com/JaKooLit/Hyprland-Dots), pensée pour Debian.

### Fonctionnalités

- barre Waybar « Deblestia Bar » verticale et flottante sur le côté gauche,
  inspirée de Caelestia ;
- bureaux avec icônes des applications ouvertes ;
- mini-lecteur MPRIS inspiré de Spotify ;
- lecteur multimédia compact adapté à la barre latérale ;
- commandes précédent, lecture/pause et suivant ;
- panneau multimédia GTK avec volume et sortie audio ;
- couleurs pilotées par `panel-colors.css`.

### Installation

Cette configuration suppose une session Hyprland et les dotfiles KooL déjà
installés. Elle nécessite notamment `waybar`, `playerctl`, `cava`, `jq`,
`python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`, `wireplumber`, `pulseaudio-utils`,
`rofi`, `kitty` et `btop`.

```bash
sudo apt update
sudo apt install waybar playerctl cava jq python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 wireplumber pulseaudio-utils rofi kitty btop
```

```bash
git clone --depth 1 https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git
cd Debian-Hyprland-Custom
./install-deblestia-bar.sh check
./install-deblestia-bar.sh
```

L’installateur sauvegarde la configuration Waybar active avant de poser les
fichiers. Déconnectez-vous puis reconnectez-vous si Waybar ne se recharge pas.

### Commandes du lecteur

- clic sur le titre : ouvre le panneau multimédia ;
- clic du milieu sur le titre : lecture/pause ;
- clic droit sur le titre : titre suivant ;
- boutons dédiés : précédent, lecture/pause et suivant.

## Crédits

- Projet et dotfiles originaux : [@JaKooLit](https://github.com/JaKooLit)
- Personnalisation Debian : [@kebemouhamet08-gif](https://github.com/kebemouhamet08-gif)
- Galerie et principes de collection : [ydots](https://github.com/hugthebox/ydots)
- Architecture Quickshell, panneaux configurables et services locaux étudiés dans
  [end4-pC](https://github.com/pctrade/end4-pC), dérivé d'illogical-impulse.
- Thèmes instantanés et architecture modulaire étudiés dans
  [Lyne Dots](https://github.com/caioax/lyne-dots) et
  [Minflair](https://github.com/t4lentles5/minflair).
- Dédicace aux communautés Debian, Hyprland et Caelestia, dont le travail rend
  cette configuration possible.

Ce dépôt redistribue des éléments adaptés du projet original sous GNU GPL v3.
Consultez [LICENSE.md](LICENSE.md).
