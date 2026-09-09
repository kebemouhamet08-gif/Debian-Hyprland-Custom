# Test dans VirtualBox

1. Créez une VM Debian 13 GNOME avec 4 processeurs et 6 Gio de RAM si possible.
2. VM éteinte, choisissez VMSVGA, 128 Mio de mémoire vidéo et activez la 3D.
3. Démarrez Debian, installez les Guest Additions, puis vérifiez `glxinfo -B`
   et `ls /dev/dri`. `llvmpipe` indique un rendu logiciel limité.
4. Clonez le dépôt et lancez `./install.sh diagnostic`, puis `./install.sh`.
5. Le profil VM proposé est LITE : fond statique, effets réduits et MPVpaper
   facultatif. Les fonctions lourdes restent accessibles en mode manuel.
6. Déconnectez-vous de GNOME et sélectionnez Hyprland dans GDM.
7. Si Hyprland échoue, revenez à GNOME depuis le même menu de session. Deblestia
   ne supprime ni GNOME ni GDM.

VirtualBox ne garantit pas toutes les fonctions de Hyprland. Pour une vidéo plus
fiable, QEMU/KVM avec virtio et accélération 3D peut mieux convenir.
