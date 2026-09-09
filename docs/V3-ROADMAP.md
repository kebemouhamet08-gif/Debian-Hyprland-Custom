# Feuille de route v3 — Debian Next

La V3 sera un composant indépendant des trois interfaces conservées. Elle ne
remplacera aucune interface et conservera ses propres
réglages, sauvegardes, manifeste et installateur.

## Direction initiale

- construire un centre de personnalisation unique pour les thèmes, profils et fonds ;
- conserver la compatibilité Debian et `apt` comme référence ;
- permettre le retour vers la V2 sans supprimer ses fichiers ;
- préférer des composants indépendants à un remplacement global de la session ;
- documenter chaque adaptation externe et sa licence avant intégration.

## Étapes

### 1. Socle V3

- manifeste de composants ;
- commandes `check`, `install`, `status` et `restore` ;
- état et sauvegardes dans `~/.config/debian-next-v3` ;
- mode `--dry-run` avant toute écriture.

### 2. Centre de personnalisation

- application GTK dédiée aux périphériques USB, HID, écrans et manettes ;
- vue unique pour les thèmes, couleurs, fonds et profils écran ;
- aperçu avant application ;
- application atomique et annulation immédiate.

État : le centre de contrôle matériel existe dans `config/v3/device-center.py`.
Il consomme en priorité l’inventaire physique agrégé par `pericored`, sépare les
interfaces externes de clavier, souris et manette, puis conserve les outils Debian
comme repli. L’onglet Affichage ouvre MPVpaper Engine. Les commandes propriétaires
ne sont jamais envoyées sans backend et protocole identifiés.

### 3. Profils de session

- profils portable, bureau et multi-écrans ;
- choix indépendant du shell, de la barre et du moteur de fond ;
- une seule expérience active à la fois, sans désinstallation des autres.

### 3.1 Contrôles matériels

- luminosité et entrée écran via DDC/CI avec `ddcutil` ;
- RGB via OpenRGB quand le périphérique est pris en charge ;
- remappage et macros via evdev/uinput avec permissions explicites ;
- profils clavier, souris et manette sauvegardés séparément ;
- détection des changements branchement/débranchement via udev.
- détection des appareils Bluetooth via BlueZ et `bluetoothctl`.

### 3.2 Fondation PeriphX

- [x] daemon `pericored` avec protocole IPC JSONL versionné (`ping`, `version`,
  inventaire, état, inspection) ;
- [x] modèle `Device` enrichi avec connexion, driver, capabilities et batterie ;
- [x] registre de drivers avec `generic-hid` prioritaire et fallback lecture seule ;
- [x] CLI `periphx inspect` sans envoi de reports propriétaires ;
- [x] descripteurs HID décodés, empreinte SHA-256, interfaces physiques et tests ;
- [x] agrégation des nœuds `event`, `mouse` et `hidraw` d’un périphérique physique ;
- [x] capture bornée des reports entrants avec ouverture `O_RDONLY` uniquement ;
- [x] manifests de pilotes custom stricts, atomiques et limités à la lecture ;
- [x] socket utilisateur privé, requêtes IPC bornées et service systemd durci ;
- [ ] premier driver matériel avec opérations d’écriture validées.

### 4. Thèmes et couleurs

- format de thème V3 commun ;
- migration contrôlée des thèmes HyDE déjà téléchargés ;
- palettes statiques et dynamiques avec contraste vérifié.

### 5. Validation

- tests d'installation isolée ;
- restauration après interruption ;
- vérification de coexistence V1/V2/V3 ;
- audit Debian, licences et dépendances.

## État

- [x] structure et manifeste V3 ;
- [x] application graphique de détection des périphériques ;
- [x] installateur V3 isolé, mode simulation et restauration ;
- [x] centre matériel PeriphX et lien vers le moteur d’affichage ;
- [x] moteur couleur MPVpaper temps réel et profils par écran ;
- [ ] centre de personnalisation unifié complet ;
- [ ] profils de session ;
- [ ] moteur de thèmes V3 ;
- [ ] validation de coexistence.
