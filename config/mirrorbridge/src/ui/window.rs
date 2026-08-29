use crate::backends;
use crate::devices::android;
use gtk::prelude::*;
use gtk::{
    Align, Application, ApplicationWindow, Box as GtkBox, Button, Label, ListBox, ListBoxRow,
    Orientation, ScrolledWindow, SelectionMode,
};

pub fn build_ui(app: &Application) {
    let window = ApplicationWindow::builder()
        .application(app)
        .title("MirrorBridge")
        .default_width(900)
        .default_height(620)
        .build();

    let root = GtkBox::new(Orientation::Vertical, 14);
    root.set_margin_top(20);
    root.set_margin_bottom(20);
    root.set_margin_start(20);
    root.set_margin_end(20);

    let title = Label::new(None);
    title.set_markup("<span size=\"xx-large\" weight=\"bold\">MirrorBridge</span>");
    title.set_xalign(0.0);
    root.append(&title);

    let subtitle = Label::new(Some(
        "Recopie et contrôle de smartphones Android et iPhone sous Linux",
    ));
    subtitle.set_xalign(0.0);
    subtitle.set_wrap(true);
    root.append(&subtitle);

    let actions = GtkBox::new(Orientation::Horizontal, 10);
    let refresh_button = Button::with_label("Actualiser Android");
    let airplay_button = Button::with_label("Démarrer AirPlay");
    airplay_button.set_sensitive(backends::command_available("uxplay"));
    actions.append(&refresh_button);
    actions.append(&airplay_button);
    root.append(&actions);

    let status = Label::new(Some("Initialisation…"));
    status.set_xalign(0.0);
    status.set_wrap(true);
    root.append(&status);

    let android_title = Label::new(None);
    android_title.set_markup("<span size=\"large\" weight=\"bold\">Appareils Android</span>");
    android_title.set_xalign(0.0);
    root.append(&android_title);

    let device_list = ListBox::new();
    device_list.set_selection_mode(SelectionMode::None);
    let scroll = ScrolledWindow::builder()
        .hexpand(true)
        .vexpand(true)
        .child(&device_list)
        .build();
    root.append(&scroll);

    {
        let list = device_list.clone();
        let status = status.clone();
        refresh_button.connect_clicked(move |_| refresh_android_devices(&list, &status));
    }

    {
        let status = status.clone();
        airplay_button.connect_clicked(move |_| match backends::ios::launch_uxplay() {
            Ok(()) => status.set_text(
                "AirPlay est démarré. Sur l’iPhone : Centre de contrôle → Recopie de l’écran → MirrorBridge.",
            ),
            Err(error) => status.set_text(&format!("Erreur UxPlay : {error}")),
        });
    }

    refresh_android_devices(&device_list, &status);
    if !backends::command_available("uxplay") {
        status.set_text("UxPlay n’est pas installé. Android reste disponible avec ADB et scrcpy.");
    }

    window.set_child(Some(&root));
    window.present();
}

fn refresh_android_devices(list: &ListBox, status: &Label) {
    while let Some(child) = list.first_child() {
        list.remove(&child);
    }

    if !android::adb_available() {
        status.set_text("ADB n’est pas disponible. Installe-le avec : sudo apt install adb");
        return;
    }

    match android::list_android_devices() {
        Ok(devices) if devices.is_empty() => status
            .set_text("Aucun Android détecté. Branche le téléphone et active le débogage USB."),
        Ok(devices) => {
            let total = devices.len();
            for device in devices {
                add_android_device_row(list, device, status);
            }
            status.set_text(&format!("{total} appareil(s) Android détecté(s)."));
        }
        Err(error) => status.set_text(&format!("Erreur ADB : {error}")),
    }
}

fn add_android_device_row(list: &ListBox, device: android::AndroidDevice, global_status: &Label) {
    let row = ListBoxRow::new();
    let content = GtkBox::new(Orientation::Horizontal, 16);
    content.set_margin_top(12);
    content.set_margin_bottom(12);
    content.set_margin_start(12);
    content.set_margin_end(12);

    let info = GtkBox::new(Orientation::Vertical, 4);
    info.set_hexpand(true);

    let name = Label::new(None);
    name.set_markup(&format!(
        "<span weight=\"bold\" size=\"large\">{}</span>",
        gtk::glib::markup_escape_text(&device.model)
    ));
    name.set_xalign(0.0);
    info.append(&name);

    let serial = Label::new(Some(&format!("ID : {}", device.serial)));
    serial.set_xalign(0.0);
    info.append(&serial);

    let state_text = match device.state.as_str() {
        "device" => "Prêt",
        "unauthorized" => "Non autorisé — confirme l’autorisation sur le téléphone",
        "offline" => "Hors ligne",
        other => other,
    };
    let state = Label::new(Some(&format!("État : {state_text}")));
    state.set_xalign(0.0);
    info.append(&state);
    content.append(&info);

    let connect_button = Button::with_label("Connecter");
    connect_button.set_valign(Align::Center);
    connect_button.set_sensitive(device.is_ready() && backends::command_available("scrcpy"));

    {
        let serial = device.serial.clone();
        let status = global_status.clone();
        connect_button.connect_clicked(move |_| {
            status.set_text(&format!("Connexion à {serial}…"));
            match backends::android::launch_scrcpy(&serial) {
                Ok(()) => status.set_text(&format!("MirrorBridge est connecté à {serial}.")),
                Err(error) => status.set_text(&format!("Erreur scrcpy : {error}")),
            }
        });
    }

    content.append(&connect_button);
    row.set_child(Some(&content));
    list.append(&row);
}
