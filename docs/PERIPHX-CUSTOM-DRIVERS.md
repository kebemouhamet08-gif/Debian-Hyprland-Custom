# Pilotes custom PeriphX

PeriphX accepte des manifests JSON locaux dans
`$XDG_CONFIG_HOME/periphx/drivers.d` (par défaut
`~/.config/periphx/drivers.d`). Ces manifests identifient précisément un appareil
et sélectionnent un pilote déclaratif. Ils ne chargent aucun exécutable et restent
obligatoirement en lecture seule.

```json
{
  "schema_version": 1,
  "name": "example-mouse",
  "version": "1.0.0",
  "match": {
    "vendor_id": "1234",
    "product_id": "5678",
    "interface_number": "01",
    "descriptor_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "capabilities": [
    "device.info",
    "hid.inspect",
    "hid.report_descriptor"
  ]
}
```

Le VID et le PID exacts sont obligatoires. L'interface et l'empreinte du
descripteur sont recommandées pour éviter qu'un manifest ne corresponde à une
révision matérielle différente.

```bash
periphx-cli drivers validate driver.json
periphx-cli drivers install driver.json
periphx-cli drivers update driver.json
periphx-cli drivers list
periphx-cli drivers remove example-mouse
```

L'installation et la mise à jour utilisent un remplacement atomique, puis
demandent au daemon de recharger son registre. Un daemon plus ancien peut
nécessiter un redémarrage manuel. Toute capability d'écriture est rejetée ; une
future écriture HID devra être implémentée dans un pilote audité et compilé avec
un matching plus strict et des validations propres au protocole matériel.
