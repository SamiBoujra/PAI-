import sys
import tempfile
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QDoubleSpinBox, QLineEdit, QComboBox, QLabel
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

def fmt_price(x):
    try:
        return f"${x:,.0f}"
    except Exception:
        return "$0"


class CartographyDynamic(QWidget):
    """Carte Folium dynamique mise à jour à chaque changement de filtre."""

    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df

        # ---- Filtres ----
        self.spin_min_price = QDoubleSpinBox()
        self.spin_min_price.setRange(0, 1e8)
        self.spin_min_price.setPrefix("Min $")
        self.spin_min_price.valueChanged.connect(self.update_map)

        self.spin_max_price = QDoubleSpinBox()
        self.spin_max_price.setRange(0, 1e8)
        self.spin_max_price.setPrefix("Max $")
        self.spin_max_price.valueChanged.connect(self.update_map)

        self.spin_min_beds = QDoubleSpinBox()
        self.spin_min_beds.setRange(0, 50)
        self.spin_min_beds.setPrefix("Min Beds ")
        self.spin_min_beds.valueChanged.connect(self.update_map)

        self.spin_max_beds = QDoubleSpinBox()
        self.spin_max_beds.setRange(0, 50)
        self.spin_max_beds.setPrefix("Max Beds ")
        self.spin_max_beds.valueChanged.connect(self.update_map)

        self.edit_city = QLineEdit()
        self.edit_city.setPlaceholderText("Ville contient…")
        self.edit_city.textChanged.connect(self.update_map)

        self.combo_state = QComboBox()
        self.combo_state.addItem("")
        states = sorted(map(str, df["State"].dropna().unique()))
        self.combo_state.addItems(states)
        self.combo_state.currentTextChanged.connect(self.update_map)

        # ---- Carte ----
        self.web = QWebEngineView()

        # ---- Layout ----
        form = QFormLayout()
        form.addRow("Prix ($)", self._row(self.spin_min_price, self.spin_max_price))
        form.addRow("Chambres (Beds)", self._row(self.spin_min_beds, self.spin_max_beds))
        form.addRow("Ville", self.edit_city)
        form.addRow("État", self.combo_state)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(QLabel("Carte des biens filtrés :"))
        lay.addWidget(self.web, stretch=1)

        # Génération initiale
        self.update_map()

    def _row(self, *widgets):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for wd in widgets:
            h.addWidget(wd)
        return w

    def filtered_df(self):
        df = self.df
        min_price = self.spin_min_price.value() or None
        max_price = self.spin_max_price.value() or None
        min_beds = self.spin_min_beds.value() or None
        max_beds = self.spin_max_beds.value() or None
        city = self.edit_city.text().strip()
        state = self.combo_state.currentText().strip()

        if min_price:
            df = df[df["Price"] >= min_price]
        if max_price:
            df = df[df["Price"] <= max_price]
        if min_beds:
            df = df[df["Beds"] >= min_beds]
        if max_beds:
            df = df[df["Beds"] <= max_beds]
        if city:
            df = df[df["City"].astype(str).str.contains(city, case=False, na=False)]
        if state:
            df = df[df["State"] == state]
        return df

    def update_map(self):
            """Met à jour la carte à partir du DataFrame filtré."""
            try:
                df_f = self.filtered_df()

                # Vérifier que le DataFrame est valide
                if df_f.empty or not {"Latitude", "Longitude"}.issubset(df_f.columns):
                    # Créer une carte vide
                    m = folium.Map(location=[39.5, -98.35], zoom_start=4, tiles="CartoDB positron")
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
                    m.save(tmp.name)
                    self.web.setUrl(QUrl.fromLocalFile(tmp.name))
                    return

                # Créer la carte
                m = folium.Map(location=[39.5, -98.35], zoom_start=4, tiles="CartoDB positron")
                cluster = MarkerCluster().add_to(m)

                # Limiter le nombre de points pour éviter les ralentissements
                for _, row in df_f.head(3000).iterrows():
                    try:
                        lat = float(row["Latitude"])
                        lon = float(row["Longitude"])
                    except Exception:
                        continue

                    html = (
                        f"<b>{row.get('Address','')}</b><br>"
                        f"{row.get('City','')}, {row.get('State','')} ({row.get('Zip Code','')})<br>"
                        f"Price: {fmt_price(row.get('Price', 0))}<br>"
                        f"Beds: {row.get('Beds','?')} | Baths: {row.get('Baths','?')} | "
                        f"Living Space: {row.get('Living Space','?')} ft²"
                    )
                    folium.Marker([lat, lon], popup=html).add_to(cluster)

                # Sauvegarde temporaire et affichage dans le widget web
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
                m.save(tmp.name)
                self.web.setUrl(QUrl.fromLocalFile(tmp.name))

            except Exception as e:
                print(f"[ERREUR update_map] {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    df = pd.read_csv(r"C:\vscode\projet PAI\American_Housing_Data_20231209.csv")
    w = CartographyDynamic(df)
    w.setWindowTitle("Cartographie dynamique - US Real Estate")
    w.resize(900, 700)
    w.show()
    sys.exit(app.exec())
