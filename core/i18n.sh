#!/usr/bin/env bash

# Shared translations for Deblestia command-line tools.
deblestia_detect_language() {
    local requested="${DEBLESTIA_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}"
    requested="${requested,,}"
    case "$requested" in
        en|en_*|en-*) printf 'en\n' ;;
        *) printf 'fr\n' ;;
    esac
}

DEBLESTIA_LANG="$(deblestia_detect_language)"
export DEBLESTIA_LANG

deblestia_set_language() {
    case "${1,,}" in
        en|english) DEBLESTIA_LANG=en ;;
        fr|français|francais|french) DEBLESTIA_LANG=fr ;;
        *) return 2 ;;
    esac
    export DEBLESTIA_LANG
}

deblestia_t() {
    local key="$1"
    shift || true
    local text
    if [ "$DEBLESTIA_LANG" = en ]; then
        case "$key" in
            usage) text='Usage: %s [--lang en|fr] [menu|diagnostic|plan|automatic|manual|component ID|contribute|uninstall]' ;;
            analyzing) text='Non-destructive system analysis…' ;;
            confirmation_required) text='Interactive confirmation required. Use DEBLESTIA_ASSUME_YES=1 for automation.' ;;
            continue_plan) text='Continue with this plan? [y/N] ' ;;
            deps_present) text='Debian dependencies are already installed.' ;;
            deps_needed) text='Required Debian packages: %s' ;;
            package_missing) text='%s is unavailable in the configured repositories. Enable Debian backports explicitly if needed.' ;;
            manual_command) text='Manual command:' ;;
            automatic_refused) text='Automatic installation stopped because of the reported compatibility issue.' ;;
            profile) text='Profile: %s' ;;
            gnome_kept) text='GNOME and the current display manager will be preserved.' ;;
            components_proposed) text='Suggested components: %s' ;;
            dependencies_install) text='Dependencies to install: %s' ;;
            none) text='none' ;;
            dry_run_done) text='Dry run complete: no changes were made.' ;;
            deps_prompt) text='Dependencies: [A] automatic, [M] commands, [S] skip: ' ;;
            cancelled) text='Installation cancelled.' ;;
            components_deferred) text='Components postponed until dependencies are installed.' ;;
            install_done) text='Installation complete. GNOME remains available in the display manager.' ;;
            unknown_component) text='Unknown component: %s' ;;
            component) text='Component: %s' ;;
            manual_title) text='Manual installation' ;;
            back) text='Back' ;;
            choice) text='Choice: ' ;;
            unknown_choice) text='Unknown choice.' ;;
            automatic_menu) text='Automatic installation' ;;
            manual_menu) text='Manual installation' ;;
            contribution_menu) text='Contribution mode' ;;
            diagnostic_menu) text='Hardware diagnostic' ;;
            restore_menu) text='Repair / restore' ;;
            uninstall_menu) text='Uninstall' ;;
            quit_menu) text='Quit' ;;
            bad_language) text='Unsupported language: %s (use en or fr).' ;;
            installing) text='Installing: %s' ;;
            installer_missing) text='ERROR    unknown component or missing installer: %s' ;;
            critical_failure) text='CRITICAL FAILURE: %s' ;;
            optional_failure) text='OPTIONAL unavailable: %s. General installation will continue.' ;;
            no_installation) text='No unified installation is recorded. Legacy installers remain managed by their restore command.' ;;
            installed_components) text='Recorded components: %s' ;;
            restore_prompt) text='Restore without removing GNOME or system packages? [y/N] ' ;;
            confirmation_short) text='Interactive confirmation required.' ;;
            restored) text='Restored: %s' ;;
            restore_unavailable) text='Restore unavailable: %s' ;;
            state_removed) text='Deblestia state removed. GNOME, GDM and existing packages were preserved.' ;;
            contribution_help) text='Deblestia contribution mode\n  ./contribute.sh report  Anonymized hardware report, displayed locally\n  ./contribute.sh test    Installer foundation validation\n\nNo data is sent automatically.' ;;
            *) text="$key" ;;
        esac
    else
        case "$key" in
            usage) text='Usage : %s [--lang en|fr] [menu|diagnostic|plan|automatic|manual|component ID|contribute|uninstall]' ;;
            analyzing) text='Analyse non destructive de la machine…' ;;
            confirmation_required) text='Confirmation interactive requise. Utilisez DEBLESTIA_ASSUME_YES=1 en automatisation.' ;;
            continue_plan) text='Continuer avec ce plan ? [o/N] ' ;;
            deps_present) text='Dépendances Debian déjà présentes.' ;;
            deps_needed) text='Paquets Debian nécessaires : %s' ;;
            package_missing) text='%s est absent des dépôts configurés. Activez explicitement les backports Debian si nécessaire.' ;;
            manual_command) text='Commande manuelle :' ;;
            automatic_refused) text='Installation automatique refusée à cause du blocage indiqué.' ;;
            profile) text='Profil : %s' ;;
            gnome_kept) text='GNOME et le display manager actuel seront conservés.' ;;
            components_proposed) text='Composants proposés : %s' ;;
            dependencies_install) text='Dépendances à installer : %s' ;;
            none) text='aucune' ;;
            dry_run_done) text='Simulation terminée : aucune modification effectuée.' ;;
            deps_prompt) text='Dépendances : [A] automatique, [M] commandes, [S] ignorer : ' ;;
            cancelled) text='Installation annulée.' ;;
            components_deferred) text="Composants reportés jusqu'à la présence des dépendances." ;;
            install_done) text='Installation terminée. GNOME reste disponible dans le gestionnaire de connexion.' ;;
            unknown_component) text='Composant inconnu : %s' ;;
            component) text='Composant : %s' ;;
            manual_title) text='Installation manuelle' ;;
            back) text='Retour' ;;
            choice) text='Choix : ' ;;
            unknown_choice) text='Choix inconnu.' ;;
            automatic_menu) text='Installation automatique' ;;
            manual_menu) text='Installation manuelle' ;;
            contribution_menu) text='Mode contribution' ;;
            diagnostic_menu) text='Diagnostic matériel' ;;
            restore_menu) text='Réparation / restauration' ;;
            uninstall_menu) text='Désinstallation' ;;
            quit_menu) text='Quitter' ;;
            bad_language) text='Langue non prise en charge : %s (utilisez en ou fr).' ;;
            installing) text='Installation : %s' ;;
            installer_missing) text='ERREUR   composant inconnu ou installateur absent : %s' ;;
            critical_failure) text='ÉCHEC critique : %s' ;;
            optional_failure) text='OPTIONNEL indisponible : %s. Installation générale poursuivie.' ;;
            no_installation) text='Aucune installation unifiée enregistrée. Les anciens installateurs restent gérés par leur commande restore.' ;;
            installed_components) text='Composants enregistrés : %s' ;;
            restore_prompt) text='Restaurer sans supprimer GNOME ni les paquets système ? [o/N] ' ;;
            confirmation_short) text='Confirmation interactive requise.' ;;
            restored) text='Restauré : %s' ;;
            restore_unavailable) text='Restauration non disponible : %s' ;;
            state_removed) text='État Deblestia retiré. GNOME, GDM et les paquets existants sont conservés.' ;;
            contribution_help) text='Mode contribution Deblestia\n  ./contribute.sh report  Rapport matériel anonymisé, affiché localement\n  ./contribute.sh test    Validation du socle installateur\n\nAucune donnée n’est envoyée automatiquement.' ;;
            *) text="$key" ;;
        esac
    fi
    printf "$text" "$@"
}
