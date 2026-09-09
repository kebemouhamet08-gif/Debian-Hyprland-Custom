# Feuille de route v2 — Custom Debian V2 Immersive

La v2 est une expérience autonome construite autour de Caelestia, MPVpaper Engine
et de concepts adaptés de HyDE. Elle constitue le mode « Custom Debian V2
Immersive » et coexiste avec Nova 2 et Nova Shell Custom Debian. Elle ne reprend
ni l'installateur Arch Linux ni ses commandes `pacman`/AUR.

## Principes

- Debian reste la plateforme de référence et `apt` le gestionnaire de paquets.
- Chaque version `vN` est un choix utilisateur autonome, installable séparément.
- Une nouvelle version ajoute des possibilités sans supprimer les précédentes.
- Les données, réglages, sauvegardes et installateurs des versions sont isolés.
- Chaque composant peut être installé, testé et restauré séparément.
- Aucun installateur ne remplace un fichier utilisateur sans sauvegarde préalable.
- Les réglages utilisateur sont séparés des fichiers distribués par le projet.
- Nova 2 reste installable avec `install.sh`, indépendamment du cycle de la v2.
- Les adaptations externes conservent leurs crédits et licences.

## Étapes

### 1. Socle d'installation modulaire

- créer un manifeste Debian des composants et dépendances ;
- ajouter des commandes `check`, `install`, `restore` et `status` ;
- centraliser les sauvegardes et produire un journal d'installation ;
- rendre les installateurs existants réexécutables sans doublons.

Validation : une simulation ne modifie rien, deux installations successives donnent
le même résultat et chaque fichier remplacé est restaurable.

### 2. Moteur de thèmes

- définir un format de thème commun pour GTK, Qt, Hyprland, Caelestia/Waybar,
  Kitty, Rofi et les fonds d'écran ;
- installer, activer et supprimer un thème sans toucher aux autres profils ;
- maintenir un thème commun aux trois interfaces conservées.

Validation : le changement de thème est atomique et le retour au thème précédent
fonctionne sans reconnexion lorsque les applications le permettent.

### 3. Couleurs dynamiques inspirées de Wallbash

- extraire une palette depuis le fond fixe ou une image de la vidéo MPVpaper ;
- générer des variables partagées pour Caelestia, Waybar, GTK, Rofi et Kitty ;
- proposer les modes clair, sombre, automatique et contraste renforcé ;
- mettre en cache les palettes et limiter les recalculs.

Validation : un changement de fond actualise toutes les surfaces prises en charge,
avec un contraste lisible et sans redémarrage complet de la session.

### 4. Centre de personnalisation

- réunir thèmes, fonds, palettes, écrans et profils dans une interface cohérente ;
- conserver MPVpaper Engine comme moteur spécialisé pour les vidéos ;
- afficher un aperçu avant application et permettre l'annulation immédiate.

Validation : tous les réglages persistants restent cohérents après reconnexion et
sur une configuration multi-écrans.

### 5. Profils de barre et de shell

- permettre de choisir Caelestia ou Waybar sans désinstaller l'autre ;
- fournir plusieurs dispositions Waybar et partager les actions communes ;
- intégrer le fond vidéo aléatoire et les couleurs dynamiques partout.

Validation : un seul shell ou une seule barre est actif à la fois, et le changement
de profil n'altère pas les réglages des autres profils.

### 6. Sélecteurs et automatisations

- adapter les sélecteurs Rofi utiles de HyDE ;
- ajouter profils écran, économie d'énergie, OLED et portable/bureau ;
- exposer les actions par raccourcis, interface et ligne de commande.

Validation : les commandes fonctionnent avec et sans interface graphique et
retournent un état exploitable en cas d'erreur.

### 7. Qualité, coexistence et publication

- ajouter tests de syntaxe, tests d'installation isolée et contrôles de restauration ;
- documenter l'installation, la désinstallation et le passage volontaire entre
  les profils v1 et v2 ;
- auditer licences, crédits, dépendances et compatibilité Debian ;
- publier une préversion avant de déclarer la v2 stable.

Validation : installation propre, mise à niveau et coexistence avec la v1 sont
testées sans dépendance entre les deux versions.

## État actuel

- [x] profil Caelestia sans suppression de la v1 ;
- [x] MPVpaper Engine et profils par écran ;
- [x] suggestions personnalisées et renouvelées ;
- [x] intégration du fond vidéo aléatoire dans les Waybar fournies ;
- [x] étape 1 — socle modulaire (`check`, `install`, `status`, `restore`,
  `--dry-run`, manifeste Debian, sauvegardes et journal séparés) ;
- [x] catalogue initial des thèmes officiels HyDE dans `config/v2/themes.tsv` ;
- [ ] étape 2 — moteur de thèmes ;
- [ ] étape 3 — couleurs dynamiques ;
- [ ] étape 4 — centre de personnalisation ;
- [ ] étape 5 — profils de barre et de shell ;
- [ ] étape 6 — sélecteurs et automatisations ;
- [ ] étape 7 — qualité, coexistence et publication.

## Référence

HyDE sert de référence d'architecture et d'expérience utilisateur. Toute reprise de
code doit être examinée séparément pour vérifier sa portabilité Debian et sa licence.
