# HUD de bureau MPVpaper Engine

Le HUD utilise une surface Wayland transparente séparée de la vidéo. Il reste
affiché quand le fond est arrêté ou en pause, avec une image fixe, avec un autre
gestionnaire de fond, ou sans fond configuré dans MPVpaper Engine. Le service
`mpvpaper-engine.service` doit rester actif. Fermer l’interface ne ferme pas le HUD.

La surface se trouve au-dessus du fond et sous les fenêtres des applications.
Elle ne capture ni les clics ni le clavier. Elle suit les écrans connectés.
Il ne s’agit pas d’un moteur compatible avec les skins Rainmeter.

## Régler le HUD

Ouvrir **Desktop HUD Editor** dans MPVpaper Engine (également accessible depuis
les paramètres). L’ancien deuxième panneau de réglages a été remplacé par ce
lien pour éviter les valeurs contradictoires.

La molette et le geste de défilement du pavé tactile font défiler le formulaire,
même au-dessus des curseurs et des champs numériques. Pour modifier ces valeurs,
utiliser le clic, le glissement du curseur ou le clavier. Les barres de défilement
restent visibles lorsque le contenu dépasse la page.

1. Choisir **Réglages globaux (*)** ou un écran précis. Les réglages propres à un
   écran sont prioritaires ; modifier les valeurs globales ne les efface pas.
2. Régler X/Y, ancrage, échelle, opacité, textes et couleurs. X/Y vont de 0 à 1
   relativement à l’écran, en désignant le point d’ancrage sélectionné.
   L’échelle et les marges utilisent les pixels logiques, donc tiennent compte
   de la mise à l’échelle et de la rotation du moniteur.
3. L’aperçu est temporaire. **Appliquer** enregistre ; **Annuler** restaure les
   valeurs enregistrées. **Valeurs par défaut** prépare une réinitialisation qui
   doit elle aussi être appliquée. Changer d’écran abandonne son aperçu.

Pour respecter les coordonnées exactes, désactiver **Éviter les panneaux** et
**Alignement automatique**. Avec ces options activées, l’éditeur indique les
coordonnées ajustées. Une échelle trop grande peut dépasser l’écran : elle n’est
pas réduite silencieusement. Les textes trop longs sont tronqués dans la largeur
du widget pour conserver une géométrie stable.

**Couleurs fixes personnalisées** empêche les couleurs du HUD de suivre les
changements de palette du bureau. **Palette du bureau** les suit volontairement.
Le cadrage, le zoom, la vitesse et les filtres vidéo ne modifient jamais le HUD.

## Dépendances et mise à jour

Le HUD requiert GTK3, Cairo/Pango et GTK Layer Shell, indépendamment de
l’interface principale GTK4. Les paquets supplémentaires Debian sont :

```bash
sudo apt install gir1.2-gtklayershell-0.1 python3-gi-cairo
```

Après installation de ces dépendances, fermer l’interface et mettre à jour
les modules depuis le dépôt avec l’installateur existant. Ces options évitent
de retélécharger l’environnement vidéo et d’activer les services pendant la copie :

```bash
MPVPAPER_ENGINE_SKIP_DOWNLOADER_SETUP=1 MPVPAPER_ENGINE_SKIP_SYSTEMD=1 ./install-mpvpaper-engine.sh
systemctl --user restart mpvpaper-engine.service
```

La configuration reste dans le fichier habituel de MPVpaper Engine, sous
`ui.hud`, avec les particularités dans `ui.hud.outputs`. Aucun fichier de fond
d’écran n’est modifié pour afficher le HUD. Les anciens sous-titres HUD des
processus MPV réutilisés sont retirés sans retirer les autres sous-titres.

## Dépannage et validation

Si le HUD reste invisible, vérifier `./install-mpvpaper-engine.sh check`, puis
`journalctl --user -u mpvpaper-engine.service -n 50 --no-pager`.
Le HUD requiert un compositeur Wayland avec le protocole layer-shell, tel que
Hyprland ; il ne fonctionne pas dans une session GNOME standard ou X11.
Voir la [documentation GTK Layer Shell](https://github.com/wmww/gtk-layer-shell).

Tests automatisés (aucune fenêtre réelle ni modification de la session) :

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s config/mpvpaper-engine/tests
```

À vérifier dans une vraie session Hyprland : appliquer X=0,5/Y=0,5 avec ancrage
central, changer l’échelle et l’opacité, appliquer puis rouvrir l’éditeur ;
mettre la vidéo en pause puis l’arrêter ; changer son cadrage ; enfin vérifier
le passage des clics et le comportement après déconnexion/reconnexion d’un écran.
