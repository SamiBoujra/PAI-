# Exploration (E1–E4) – Application Qt (PySide6)
# ------------------------------------------------
# Fonctionnalités couvertes:
#  - E1: Structure d'application avec onglets (placeholder pour autres onglets)
#  - E2: Onglet "Exploration" listant les biens (TableView) avec attributs principaux
#  - E3: Filtres dynamiques (prix, surface, ville, revenu médian, recherche texte)
#  - E4: Tri par n'importe quelle colonne (cliquer l'entête pour trier)
#  - + Export CSV des données filtrées (utile pour E10, optionnel ici)
#
# Dépendances:
#   pip install PySide6 pandas numpy
#
# Utilisation:
#   1) Modifier le chemin DATA_PATH vers votre CSV
#   2) python app_exploration_qt.py

from __future__ import annotations
import sys
from pathlib import Path
from typing import List, Any

import numpy as np
import pandas as pd
from PySide6.QtCore import (Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
                            QSize, QUrl)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QTabWidget, QVBoxLayout, QHBoxLayout,
    QTableView, QLabel, QLineEdit, QPushButton, QFileDialog, QFormLayout,
    QDoubleSpinBox, QComboBox, QSplitter, QMessageBox, QSpinBox
)

# --------------------------- Config ---------------------------
import folium
from folium.plugins import MarkerCluster
import tempfile
import webbrowser
DATA_PATH = Path(r"C:\\vscode\\projet PAI\\American_Housing_Data_20231209.csv")  # <-- à adapter

# Colonnes attendues d'après la fiche projet / votre EDA
EXPECTED_COLUMNS = [
    "Zip Code", "Price", "Beds", "Baths", "Living Space", "Address",
    "City", "State", "Zip Code Population", "Zip Code Density", "County",
    "Median Household Income", "Latitude", "Longitude",
]

# --------------------- Modèle pandas -> Qt --------------------
class PandasModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df.reset_index(drop=True)

    # Taille
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self._df.shape[1]

    # Données
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            val = self._df.iat[index.row(), index.column()]
            # Formatage léger pour lisibilité
            if isinstance(val, (int, np.integer)):
                return f"{int(val):,}".replace(',', ' ')
            if isinstance(val, (float, np.floating)):
                return f"{float(val):,.2f}".replace(',', ' ').replace('.00', '')
            return str(val)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        else:
            return str(section + 1)

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        # Non utilisé si on passe par QSortFilterProxyModel (recommandé)
        super().sort(column, order)

    def dataframe(self) -> pd.DataFrame:
        return self._df

# -------------------- Proxy de filtrage Qt --------------------
class RealEstateFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        # Valeurs par défaut des filtres (None = désactivé)
        self.min_price = None
        self.max_price = None
        self.min_space = None
        self.max_space = None
        self.min_beds = None
        self.max_beds = None
        self.city_substr = ""  # filtre substring sur City
        self.state_exact = ""  # filtre exact via combobox
        self.min_income = None
        self.max_income = None
        self.search_text = ""   # recherche libre dans Address

    # Récupère les colonnes par nom pour éviter l'ordre imposé
    def _col(self, name: str) -> int:
        model = self.sourceModel()
        if model is None:
            return -1
        try:
            return list(model.dataframe().columns).index(name)
        except ValueError:
            return -1

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: PandasModel = self.sourceModel()
        if model is None:
            return True
        df = model.dataframe()

        def val(col_name):
            col_idx = self._col(col_name)
            if col_idx < 0:
                return None
            return df.iat[source_row, col_idx]

        # --- Filtres numériques ---
        price = val("Price")
        if price is not None and isinstance(price, (int, float, np.integer, np.floating)):
            if self.min_price is not None and price < self.min_price:
                return False
            if self.max_price is not None and price > self.max_price:
                return False

        space = val("Living Space")
        if space is not None and isinstance(space, (int, float, np.integer, np.floating)):
            if self.min_space is not None and space < self.min_space:
                return False
            if self.max_space is not None and space > self.max_space:
                return False

        beds = val("Beds")
        if beds is not None and isinstance(beds, (int, float, np.integer, np.floating)):
            if self.min_beds is not None and beds < self.min_beds:
                return False
            if self.max_beds is not None and beds > self.max_beds:
                return False

        income = val("Median Household Income")
        if income is not None and isinstance(income, (int, float, np.integer, np.floating)):
            if self.min_income is not None and income < self.min_income:
                return False
            if self.max_income is not None and income > self.max_income:
                return False

        # --- Filtres texte ---
        city = str(val("City") or "")
        if self.city_substr and self.city_substr.lower() not in city.lower():
            return False

        state = str(val("State") or "")
        if self.state_exact and state != self.state_exact:
            return False

        address = str(val("Address") or "")
        if self.search_text and self.search_text.lower() not in address.lower():
            return False

        return True

# ------------------------ UI Exploration ----------------------
class ExplorationTab(QWidget):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df

        # Modèle & proxy
        self.model = PandasModel(self.df)
        self.proxy = RealEstateFilterProxy()
        self.proxy.setSourceModel(self.model)

        # Table
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)  # E4: tri en cliquant en-tête
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(False)

        # Panneau filtres
        self._build_filters()

        # Layout avec splitter
        splitter = QSplitter()
        left = QWidget(); left.setLayout(self.filters_layout)
        splitter.addWidget(left)
        splitter.addWidget(self.table)
        splitter.setSizes([300, 900])

        # Barre d'actions (export)
        btn_export = QPushButton("Exporter CSV (filtré)")
        btn_export.clicked.connect(self.export_csv)

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        main_layout.addWidget(btn_export)
        self.setLayout(main_layout)

    def _build_filters(self):
        self.filters_layout = QFormLayout()

        # Prix min/max
        self.spin_min_price = QDoubleSpinBox(); self.spin_min_price.setRange(0, 1e9); self.spin_min_price.setPrefix("Min $"); self.spin_min_price.setDecimals(0)
        self.spin_max_price = QDoubleSpinBox(); self.spin_max_price.setRange(0, 1e9); self.spin_max_price.setPrefix("Max $"); self.spin_max_price.setDecimals(0)
        self.spin_min_price.valueChanged.connect(self._on_filters_changed)
        self.spin_max_price.valueChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("Prix ($) :"), self._row(self.spin_min_price, self.spin_max_price))

        # Surface min/max
        self.spin_min_space = QDoubleSpinBox(); self.spin_min_space.setRange(0, 1e6); self.spin_min_space.setPrefix("Min "); self.spin_min_space.setDecimals(0)
        self.spin_max_space = QDoubleSpinBox(); self.spin_max_space.setRange(0, 1e6); self.spin_max_space.setPrefix("Max "); self.spin_max_space.setDecimals(0)
        self.spin_min_space.valueChanged.connect(self._on_filters_changed)
        self.spin_max_space.valueChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("Surface (ft²) :"), self._row(self.spin_min_space, self.spin_max_space))

        # Beds min/max
        self.spin_min_beds = QDoubleSpinBox(); self.spin_min_beds.setRange(0, 50); self.spin_min_beds.setPrefix("Min "); self.spin_min_beds.setDecimals(0)
        self.spin_max_beds = QDoubleSpinBox(); self.spin_max_beds.setRange(0, 50); self.spin_max_beds.setPrefix("Max "); self.spin_max_beds.setDecimals(0)
        self.spin_min_beds.valueChanged.connect(self._on_filters_changed)
        self.spin_max_beds.valueChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("Chambres (Beds) :"), self._row(self.spin_min_beds, self.spin_max_beds))

        # Revenu médian min/max
        self.spin_min_income = QDoubleSpinBox(); self.spin_min_income.setRange(0, 1e7); self.spin_min_income.setPrefix("Min $"); self.spin_min_income.setDecimals(0)
        self.spin_max_income = QDoubleSpinBox(); self.spin_max_income.setRange(0, 1e7); self.spin_max_income.setPrefix("Max $"); self.spin_max_income.setDecimals(0)
        self.spin_min_income.valueChanged.connect(self._on_filters_changed)
        self.spin_max_income.valueChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("Revenu médian ($) :"), self._row(self.spin_min_income, self.spin_max_income))

        # Ville (substring)
        self.edit_city = QLineEdit(); self.edit_city.setPlaceholderText("Contient… (ex: New York)")
        self.edit_city.textChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("Ville (contient) :"), self.edit_city)

        # État (liste déroulante exacte)
        self.combo_state = QComboBox(); self.combo_state.addItem("")
        states = sorted(map(str, self.df["State"].dropna().unique()))
        self.combo_state.addItems(states)
        self.combo_state.currentTextChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("État (exact) :"), self.combo_state)

        # Recherche libre adresse
        self.edit_search = QLineEdit(); self.edit_search.setPlaceholderText("Recherche dans Address…")
        self.edit_search.textChanged.connect(self._on_filters_changed)
        self.filters_layout.addRow(QLabel("Recherche (Address) :"), self.edit_search)

        # Boutons actions filtres
        btn_reset = QPushButton("Réinitialiser filtres")
        btn_reset.clicked.connect(self._reset_filters)
        self.filters_layout.addRow(btn_reset)

    def _row(self, *widgets) -> QWidget:
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(0,0,0,0)
        for wd in widgets:
            lay.addWidget(wd)
        return w

    def _on_filters_changed(self):
        # Met à jour les propriétés du proxy et relance le filtrage
        self.proxy.min_price = self.spin_min_price.value() or None
        self.proxy.max_price = self.spin_max_price.value() or None
        if self.proxy.max_price == 0:
            self.proxy.max_price = None

        self.proxy.min_space = self.spin_min_space.value() or None
        self.proxy.max_space = self.spin_max_space.value() or None
        if self.proxy.max_space == 0:
            self.proxy.max_space = None

        self.proxy.min_income = self.spin_min_income.value() or None
        self.proxy.max_income = self.spin_max_income.value() or None
        if self.proxy.max_income == 0:
            self.proxy.max_income = None

        self.proxy.min_beds = self.spin_min_beds.value() or None
        self.proxy.max_beds = self.spin_max_beds.value() or None
        if self.proxy.max_beds == 0:
            self.proxy.max_beds = None

        self.proxy.city_substr = self.edit_city.text().strip()
        self.proxy.state_exact = self.combo_state.currentText().strip()
        self.proxy.search_text = self.edit_search.text().strip()

        self.proxy.invalidateFilter()

    def _reset_filters(self):
        for w in [self.spin_min_price, self.spin_max_price, self.spin_min_space, self.spin_max_space,
                  self.spin_min_income, self.spin_max_income, self.spin_min_beds, self.spin_max_beds]:
            w.blockSignals(True); w.setValue(0); w.blockSignals(False)
        self.edit_city.blockSignals(True); self.edit_city.clear(); self.edit_city.blockSignals(False)
        self.combo_state.blockSignals(True); self.combo_state.setCurrentIndex(0); self.combo_state.blockSignals(False)
        self.edit_search.blockSignals(True); self.edit_search.clear(); self.edit_search.blockSignals(False)
        self._on_filters_changed()

    def export_csv(self):
        # Exporte le contenu filtré actuel
        path, _ = QFileDialog.getSaveFileName(self, "Exporter CSV filtré", "filtered_exploration.csv", "CSV (*.csv)")
        if not path:
            return
        model: PandasModel = self.model
        df_all = model.dataframe()

        # Map des lignes visibles via le proxy
        rows: List[int] = []
        for r in range(self.proxy.rowCount()):
            src_index = self.proxy.mapToSource(self.proxy.index(r, 0))
            rows.append(src_index.row())
        df_filtered = df_all.iloc[rows].copy()
        try:
            df_filtered.to_csv(path, index=False)
            QMessageBox.information(self, "Export CSV", f"Export réussi vers:{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export CSV", f"Erreur d'export: {e}")

# ----------------------- Onglet Cartographie -------------------
class CartographyTab(QWidget):
    def __init__(self, proxy: RealEstateFilterProxy, model: PandasModel):
        super().__init__()
        self.proxy = proxy
        self.model = model

        self.btn_generate = QPushButton("Générer la carte")
        self.btn_open = QPushButton("Ouvrir la carte")
        self.btn_open.setEnabled(False)

        self.sample_spin = QSpinBox(); self.sample_spin.setRange(0, 100000); self.sample_spin.setValue(8000)
        self.sample_spin.setToolTip("0 = pas d'échantillonnage")

        self.tiles_combo = QComboBox(); self.tiles_combo.addItems([
            "openstreetmap", "CartoDB positron", "Stamen Terrain", "Stamen Toner"
        ])

        self.zoom_spin = QSpinBox(); self.zoom_spin.setRange(1, 12); self.zoom_spin.setValue(4)

        form = QFormLayout()
        form.addRow("Échantillon (n)", self.sample_spin)
        form.addRow("Fond de carte (tiles)", self.tiles_combo)
        form.addRow("Zoom initial", self.zoom_spin)
        form.addRow(self.btn_generate)
        form.addRow(self.btn_open)

        lay = QVBoxLayout(self)
        lay.addLayout(form)

        self.btn_generate.clicked.connect(self.generate_map)
        self.btn_open.clicked.connect(self.open_map)
        self._last_map_path = None

    def _filtered_dataframe(self) -> pd.DataFrame:
        df_all = self.model.dataframe()
        rows = []
        for r in range(self.proxy.rowCount()):
            src_index = self.proxy.mapToSource(self.proxy.index(r, 0))
            rows.append(src_index.row())
        return df_all.iloc[rows].copy()

    def generate_map(self):
        df_f = self._filtered_dataframe()
        n = self.sample_spin.value()
        if n > 0 and len(df_f) > n:
            df_f = df_f.sample(n, random_state=42)

        # --- Génération Folium (code fourni par l'utilisateur) ---
        def fmt_price(x):
            return f"${x:,.0f}"

        m = folium.Map(location=[39.5, -98.35], tiles=self.tiles_combo.currentText(), zoom_start=int(self.zoom_spin.value()))
        cluster = MarkerCluster().add_to(m)

        for _, row in df_f.iterrows():
            html = (
                f"<b>{row['Address']}</b><br>"
                f"{row['City']}, {row['State']} ({row['Zip Code']})<br>"
                f"Price: {fmt_price(row['Price'])}<br>"
                f"Beds: {row['Beds']} | Baths: {row['Baths']} | "
                f"Living Space: {row['Living Space']} ft²"
            )
            folium.Marker([row['Latitude'], row['Longitude']], popup=html).add_to(cluster)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix="_map_markers_cluster.html")
        m.save(tmp.name)
        self._last_map_path = tmp.name
        self.btn_open.setEnabled(True)
        QMessageBox.information(self, "Carte", f"✅ Carte générée:{self._last_map_path}")

    def open_map(self):
        if not self._last_map_path:
            return
        webbrowser.open(self._last_map_path)

class MainWindow(QMainWindow):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.setWindowTitle("US Real Estate – Exploration (E1–E4)")
        self.resize(QSize(1200, 800))

        tabs = QTabWidget()
        # Crée l'onglet Exploration et réutilise son proxy pour la carte
        exploration_tab = ExplorationTab(df)
        tabs.addTab(exploration_tab, "Exploration")  # E1–E4 implémentés ici
        tabs.addTab(CartographyTab(exploration_tab.proxy, exploration_tab.model), "Cartographie")
        tabs.addTab(QWidget(), "Corrélations")
        tabs.addTab(QWidget(), "Prédiction")

        self.setCentralWidget(tabs)

        # Menu fichier minimal (ouvrir CSV)
        open_act = QAction("Ouvrir CSV…", self)
        open_act.triggered.connect(self.open_csv)
        self.menuBar().addMenu("Fichier").addAction(open_act)

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un CSV", str(DATA_PATH.parent), "CSV (*.csv)")
        if not path:
            return
        try:
            df_new = pd.read_csv(path)
            tabs = QTabWidget()
            exploration_tab = ExplorationTab(df_new)
            tabs.addTab(exploration_tab, "Exploration")
            tabs.addTab(CartographyTab(exploration_tab.proxy, exploration_tab.model), "Cartographie")
            tabs.addTab(QWidget(), "Corrélations")
            tabs.addTab(QWidget(), "Prédiction")
            self.setCentralWidget(tabs)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le CSV:{e}")
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.setWindowTitle("US Real Estate – Exploration (E1–E4)")
        self.resize(QSize(1200, 800))

        tabs = QTabWidget()
        tabs.addTab(ExplorationTab(df), "Exploration")  # E1–E4 implémentés ici
        # Placeholders pour futurs onglets
        tabs.addTab(QWidget(), "Cartographie")
        tabs.addTab(QWidget(), "Corrélations")
        tabs.addTab(QWidget(), "Prédiction")

        self.setCentralWidget(tabs)

        # Menu fichier minimal (ouvrir CSV)
        open_act = QAction("Ouvrir CSV…", self)
        open_act.triggered.connect(self.open_csv)
        self.menuBar().addMenu("Fichier").addAction(open_act)

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un CSV", str(DATA_PATH.parent), "CSV (*.csv)")
        if not path:
            return
        try:
            df_new = pd.read_csv(path)
            self.setCentralWidget(None)
            tabs = QTabWidget()
            tabs.addTab(ExplorationTab(df_new), "Exploration")
            tabs.addTab(QWidget(), "Cartographie")
            tabs.addTab(QWidget(), "Corrélations")
            tabs.addTab(QWidget(), "Prédiction")
            self.setCentralWidget(tabs)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le CSV:\n{e}")

# --------------------------- main -----------------------------
def load_dataframe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # S'assure que les colonnes attendues existent; sinon, continue avec celles disponibles
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        print("[Avertissement] Colonnes manquantes dans le CSV:", missing)
    return df

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        df = load_dataframe(DATA_PATH)
    except Exception as e:
        QMessageBox.critical(None, "Erreur", f"Impossible de lire le CSV par défaut:\n{e}")
        sys.exit(1)

    w = MainWindow(df)
    w.show()
    sys.exit(app.exec())
