# Deblestia Nova 2

Nova 2 est le profil Waybar horizontal de Deblestia. Il coexiste uniquement avec
Custom Debian V2 Immersive et Nova Shell Custom Debian.

## Workspaces

Le module natif `hyprland/workspaces` de Waybar remplace les dix scripts sondés
chaque seconde. Il suit les événements Hyprland et affiche les états actif,
visible, vide, persistant, urgent et spécial.

- `eDP-1` : workspaces 1 à 10 ;
- `HDMI-A-1` : workspaces 11 à 20 ;
- clic gauche : activer ;
- molette : précédent/suivant dans la plage de la sortie ;
- bouton overview : ouvrir Quickshell Overview ou AGS.

Waybar 0.12 ne fournit pas de clic milieu/droit ciblé ni de tooltip individuel
sur ses boutons workspace. Il affiche aussi une représentation par fenêtre,
sans limite native à trois icônes.

Le diagnostic ponctuel de la molette s'active avec `DEBLESTIA_DEBUG=1` et écrit
dans `~/.cache/deblestia/workspaces.log`.

## Modes d'interface

```bash
~/.config/waybar/deblestia-waybar-switch.sh nova2
~/.config/waybar/deblestia-waybar-switch.sh debian-v2
~/.config/waybar/deblestia-waybar-switch.sh nova-shell
```

Le mode courant est enregistré dans
`~/.local/state/deblestia/ui-mode`. Passer à une interface Waybar arrête
uniquement Nova Shell ; passer à Nova Shell arrête Waybar.

`Super+Alt+B` (Win+Alt+B) active et mémorise Custom Debian V2 Immersive.

## Validation

```bash
jq empty "$HOME/.config/waybar/configs/[Deblestia] Nova 2"
shellcheck "$HOME/.config/hypr/scripts/deblestia-workspace-action.sh"
waybar -c "$HOME/.config/waybar/configs/[Deblestia] Nova 2" \
  -s "$HOME/.config/waybar/styles/[Deblestia] Nova 2.css"
```

Les règles de résolution et de position restent dans `monitors.conf`. Nova 2
n'écrit jamais ce fichier.
