mod backends;
mod devices;
mod ui;

use gtk::prelude::*;

fn main() {
    let app = gtk::Application::builder()
        .application_id("io.github.kebemouhamet08.MirrorBridge")
        .build();

    app.connect_activate(ui::build_ui);
    app.run();
}
