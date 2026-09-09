# MPVpaper Engine 2 — Journal de progression

## D3 — Central State et Engine IPC

- État : validé.
- Tests au checkpoint : 96/96.
- Socket Engine, état atomique, instance unique et shutdown propre validés.
- Aucun service wallpaper redémarré.

## D4 — Playback Core

- État : validé après correction de la confirmation `loadfile`.
- Cause initiale : MPV rend brièvement `path` indisponible pendant `loadfile replace`.
- Correction : attente conditionnelle bornée à 3 secondes, intervalle 75 ms, retry limité à
  `property unavailable`, comparaison de chemins locaux normalisés.
- Nouveaux tests de transition : 8/8.
- Tests au checkpoint : 129/129.
- Test réel eDP-1 A → B : réussi en 241,9 ms.
- Restauration B → A : réussie en 163,8 ms.
- PID avant/après : 2621.
- Unité : active avant, pendant et après.
- Socket : même inode et fonctionnel.
- Boucle, vitesse, pause, volume, mute et filtres couleur restaurés.
- HDMI-A-1 non modifié.

## E1 — Cache Manager

- État : validé.
- Tests au checkpoint : 141/141.
- Cache utilisateur mesuré en lecture seule : 642 729 144 octets, 1 846 entrées.
- Suggestions : 642 201 331 octets, 1 820 entrées.
- Aucun nettoyage automatique et aucune écriture dans le cache utilisateur.
- Quotas, LRU, expiration, index atomique et protection des chemins Library testés.

## E2 — Metadata et Library

- État : validé.
- Tests au checkpoint : 160/160.
- Extraction ffprobe JSON unique, fingerprint scan et signature bornée testés.
- Schéma SQLite Library complet, WAL, favoris, recherche, fichiers manquants et corbeille sûre.
- Connexions SQLite fermées sans ResourceWarning.
- Base recommendations séparée et non modifiée.
- Aucune base Library utilisateur créée pendant le checkpoint.

## F — Multi-monitor

- État : validé.
- Tests au checkpoint : 174/174.
- Détection Hyprland JSON read-only et réconciliation dynamique testées.
- Modes SAME, INDEPENDENT et DISABLED disponibles.
- Profils des écrans déconnectés conservés et restauration hotplug conditionnée par autostart.
- SYNC expérimental : correction ponctuelle au-delà de 200 ms, sans boucle permanente.

## G — Advanced Playback et Preview

- État : validé.
- Tests au checkpoint : 182/182.
- État playback rafraîchi uniquement à la demande, sans écriture haute fréquence.
- Preview subprocess MPV isolé avec play/pause/seek/mute/restart et fermeture sûre.
- Fallback miniature statique disponible.
- Embed libmpv GTK4/Wayland marqué expérimental et non sélectionné automatiquement.

## H — Smart Pause

- État : validé.
- Tests au checkpoint : 193/193.
- Raisons fullscreen, lock, suspend, DPMS, batterie et power saver empilées.
- Une raison retirée ne reprend pas la lecture si une autre reste active.
- Actions continue, reduce, pause et stop disponibles sans polling.

## I — Performance Profiles

- État : validé.
- Tests au checkpoint : 206/206.
- Profils ECO, BALANCED et QUALITY déterministes.
- AUTO explicable selon CPU, RAM, GPU, pixels, batterie et média.
- Détection `mpv --hwdec=help` bornée; aucun backend spécifique forcé.
- Réglages effectifs convertibles en options MPV.

## J — Favoris, historique et playlists

- État : validé.
- Tests au checkpoint : 225/225.
- Favoris persistants dans Library, historique par écran et raison, playlists complètes.
- Modes sequential, shuffle et smart locaux; exclusion des récents et pondération explicable.
- Intervalles 5 min à 2 h et événements login/unlock disponibles sans polling.

## K — Nouvelle GUI

- État : validé pour le parcours utilisateur principal; fonctions avancées conservées dans
  l’ancienne GUI pendant la transition.
- Tests au checkpoint : 231/231.
- Nouvelle application GTK4/libadwaita avec `Adw.NavigationSplitView`, grille Library,
  Favoris, Playlists, Récents, Écrans, Réglages et inspecteur responsive.
- Apply, Pause, Resume, Restart, Volume, Mute, Speed, Loop, Colors et profil de performance
  passent par le Core IPC; aucune logique MPV dupliquée dans GTK.
- Preview unique par sélection avec miniature/image statique comme fallback sûr.
- Scan, ffprobe, SQLite, cache et opérations Engine exécutés hors du thread GTK.
- Test réel ouverture/fermeture GTK réussi avec données isolées sous `/tmp`; fermer la GUI
  ne commande jamais l’arrêt des wallpapers.
- L’ancienne GUI et son écran Discover/WebKit ne sont pas supprimés.

## L — Theme Sync

- État : validé.
- Tests au checkpoint : 237/237.
- Analyse bornée par FFmpeg : image directe, deux frames en ECO, quatre autrement.
- Palette atomique partagée avec Waybar, Nova Shell et Wallust; chaque intégration échoue
  indépendamment sans annuler les autres.
- Garde mémoire et persistante contre les boucles wallpaper/thème.
- Le changement de PID observé au checkpoint provenait d’un reboot système à 15:45:58;
  les unités restaurées avaient `NRestarts=0` et les mêmes wallpapers/configurations.

## M — CLI, Waybar, Nova et installation

- État : validé.
- Tests au checkpoint : 240/240.
- JSON stable pour status/current/outputs/list et commande de profil via le Core IPC.
- Module Waybar dynamique, actions souris, menu rapide et patch Nova utilisant le même backend.
- Lanceur v2 par défaut avec accès explicite à l’ancienne GUI; package Python et service
  utilisateur installés sous `~/.local` sans écraser les données utilisateur.
- Installation isolée sous `/tmp` réussie, puis installation utilisateur réelle sauvegardée.

## N — Stabilisation finale

- État : validé.
- Tests finaux stricts : 246/246, `ResourceWarning` traité comme erreur.
- Config legacy migrée transactionnellement en schéma 2; sauvegarde exacte
  `config.json.v1.backup` (SHA-256 `5b240cad…f5b45`).
- 2 004 candidats recommendations copiés et validés par SQLite `quick_check=ok`; source
  legacy conservée. Library créée avec 24 médias, `quick_check=ok`, mode 0600.
- `metadata.json` legacy et sa sauvegarde sont conservés; aucun fichier média supprimé.
- Core installé et actif autour de 11 MiB; reconstruction ponctuelle des wallpapers déjà
  actifs au démarrage, sans polling.
- Course systemd/socket corrigée par attente client bornée à 750 ms; restart Core réel validé.
- PID wallpapers avant/après installation et restart Core : HDMI-A-1=2363, eDP-1=2375,
  `NRestarts=0`.
- Spam terminal MPV désactivé pour les prochains démarrages; AUTO/BALANCED limite les médias
  lourds à des réglages raisonnables lorsque le Core crée l’unité.
