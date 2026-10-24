// Construit la présentation : NODE_PATH=<node_modules> node presentation/construire_slides.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const RACINE = path.resolve(__dirname, "..");
const SKILL = process.env.PPTX_SKILL;
const { applyTheme } = require(path.join(SKILL, "scripts/apply_theme.js"));
const resume = JSON.parse(fs.readFileSync(path.join(RACINE, "reports/resume_pipeline.json"), "utf8"));
const ev = resume.evaluation;
const fr = (x, d = 0) => x.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d }).replace(/ | /g, " ");

const THEME = {
  name: "FastColis Carbone", headFontFace: "Cambria", bodyFontFace: "Calibri",
  colors: { dk1: "0B0B0B", lt1: "FFFFFF", dk2: "0F3D2E", lt2: "EEF3EE", accent1: "0F6B4F", accent2: "EB6834",
            accent3: "2A78D6", accent4: "1BAF7A", accent5: "EDA100", accent6: "6250D6", hlink: "0F6B4F", folHlink: "52514E" },
};
const HEX = THEME.colors;
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Calculateur CO2 logistique intelligent";
pres.author = "Équipe FastColis, PGE3 aivancity";
const C = pres.SchemeColor;
const W = 13.333, M = 0.6;

// ---- gabarits ------------------------------------------------------------------------------
pres.defineSlideMaster({
  title: "TITRE_SOMBRE", background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.0, w: 9.5, h: 1.9, fontSize: 44, bold: true, align: "left",
      color: C.background1, valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.1, w: 11.0, h: 2.4, fontSize: 18,
      color: "C9DCD2", valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENU", background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.4, w: W - 2 * M, h: 0.95, fontSize: 30, bold: true, align: "left",
      color: C.text2, valign: "middle", margin: 0 }, text: "" } },
    { text: { text: "FastColis · Calculateur CO₂ · Projet Data Wrangling", options: { x: M, y: 7.02, w: 7, h: 0.3,
      fontSize: 10, color: "8A8984", margin: 0, fontFace: "Calibri" } } },
  ],
  slideNumber: { x: W - M - 0.6, y: 7.02, w: 0.6, h: 0.3, fontSize: 10, color: "8A8984", align: "right" },
});

// ---- outils --------------------------------------------------------------------------------
async function icone(Comp, couleur, taille = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + couleur, size: taille }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
function image(slide, fichier, x, y, wMax, hMax, nom) {
  const meta = require("child_process").execSync(`python3 -c "import struct,sys;f=open(sys.argv[1],'rb');f.read(16);print(*struct.unpack('>II',f.read(8)))" "${fichier}"`).toString().trim().split(" ").map(Number);
  const r = meta[0] / meta[1];
  let w = wMax, h = wMax / r;
  if (h > hMax) { h = hMax; w = hMax * r; }
  slide.addImage({ path: fichier, x: x + (wMax - w) / 2, y, w, h, objectName: nom, altText: nom });
  return { w, h };
}
const fig = (n) => path.join(RACINE, "reports/figures", n + ".png");
const cap = (n) => path.join(RACINE, "docs/captures", n + ".png");
const rogne = (n) => path.join(RACINE, "presentation", n + "_rogne.png");
function carte(slide, x, y, w, h, nom, fond = "F3F6F3") {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fond }, line: { color: fond }, rectRadius: 0.12, objectName: nom });
}
function texte(slide, t, o) { slide.addText(t, { isTextBox: true, margin: 0, fontFace: "Calibri", color: "333333", ...o }); }

(async () => {
  const ic = {
    avion: await icone(fa.FaPlane, HEX.accent2), camion: await icone(fa.FaTruck, HEX.accent3),
    bateau: await icone(fa.FaShip, HEX.accent5), cible: await icone(fa.FaBullseye, HEX.accent1),
    alerte: await icone(fa.FaExclamationTriangle, HEX.accent2), base: await icone(fa.FaDatabase, "FFFFFF"),
    loupe: await icone(fa.FaSearch, "FFFFFF"), balai: await icone(fa.FaBroom, "FFFFFF"), carte: await icone(fa.FaMapMarkedAlt, "FFFFFF"),
    robot: await icone(fa.FaRobot, "FFFFFF"), check: await icone(fa.FaCheckCircle, "FFFFFF"), envoi: await icone(fa.FaShareSquare, "FFFFFF"),
    chrono: await icone(fa.FaStopwatch, HEX.accent1), users: await icone(fa.FaUsers, HEX.accent1), velo: await icone(fa.FaBicycle, HEX.accent4),
  };

  // 1. Titre ------------------------------------------------------------------------------------
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITRE_SOMBRE", sectionTitle: "Introduction" });
  s.addText("Calculateur CO₂ logistique intelligent", { placeholder: "title" });
  s.addText([
    { text: "Projet Data Wrangling · FastColis", options: { bold: true, color: "FFFFFF", breakLine: true } },
    { text: "Kheireddine BOUADI, Maël RAZAFIMBELO, Mohamed BEN AMOR, Ael Boece NGODA LONTSI, Abdallah BENSMAIL", options: { breakLine: true, fontSize: 15 } },
    { text: "PGE3 · aivancity · octobre 2026", options: { fontSize: 15 } },
  ], { placeholder: "body" });
  s.addImage({ data: ic.avion, x: 10.9, y: 1.6, w: 1.1, h: 1.1, objectName: "icone avion" });
  s.addImage({ data: ic.camion, x: 10.9, y: 3.1, w: 1.1, h: 1.1, objectName: "icone camion" });
  s.addImage({ data: ic.bateau, x: 10.9, y: 4.6, w: 1.1, h: 1.1, objectName: "icone bateau" });
  s.addNotes("Présentation du projet CO2 : un pipeline de data wrangling qui calcule l'empreinte carbone de chaque colis, et l'interface qui la met entre les mains des clients grands comptes.");

  // 2. Message clé -----------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Introduction" });
  s.addText("L'avion pèse 84 % des émissions pour 12 % des colis", { placeholder: "title" });
  carte(s, M, 1.6, 6.0, 4.9, "carte avion");
  texte(s, "84 %", { x: M + 0.4, y: 1.9, w: 5.2, h: 1.3, fontSize: 72, bold: true, color: HEX.accent2, fontFace: "Cambria" });
  texte(s, "des émissions viennent des colis qui prennent l'avion", { x: M + 0.4, y: 3.2, w: 5.2, h: 0.5, fontSize: 16 });
  texte(s, "12 %", { x: M + 0.4, y: 4.0, w: 5.2, h: 1.2, fontSize: 60, bold: true, color: C.text2, fontFace: "Cambria" });
  texte(s, "des colis seulement, presque tous venus d'Asie", { x: M + 0.4, y: 5.2, w: 5.2, h: 0.5, fontSize: 16 });
  const tuiles = [["60 000", "colis analysés sur 12 mois"], ["49,7 t", "de CO₂e au total"],
                  ["89 g", "pour le colis médian"], [`± ${fr(ev.emission_reconstituee.erreur_mediane_pct, 1)} %`, "d'erreur médiane face à la réalité"]];
  tuiles.forEach(([v, l], i) => {
    const x = 7.1 + (i % 2) * 2.9, y = 1.6 + Math.floor(i / 2) * 2.5;
    carte(s, x, y, 2.65, 2.3, "tuile " + i, "EEF3EE");
    texte(s, v, { x: x + 0.25, y: y + 0.35, w: 2.2, h: 0.9, fontSize: 34, bold: true, color: C.accent1, fontFace: "Cambria" });
    texte(s, l, { x: x + 0.25, y: y + 1.3, w: 2.2, h: 0.8, fontSize: 14, valign: "top" });
  });
  s.addNotes("Le message principal : pour réduire le CO2 des colis, le sujet numéro un est le transport aérien des colis importés. Tout le reste du réseau, camions et dernier kilomètre, pèse 16 %.");

  // 3. Besoin ----------------------------------------------------------------------------------
  pres.addSection({ title: "Besoin et données" });
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Besoin et données" });
  s.addText("Un CO₂ par colis, même sur une chaîne incomplète", { placeholder: "title" });
  const colonnes = [
    ["Objectifs métier", ic.cible, [
      ["Comparabilité", "une méthode unique (EN 16258, facteurs ADEME) pour tous les clients"],
      ["Transparence", "chaque gramme se rattache à une étape, un véhicule, une source"],
      ["Anticipation", "estimer un envoi avant expédition pour orienter le choix du service"]]],
    ["Contraintes", ic.alerte, [
      ["Sources hétérogènes", "SAP, logs de scanners en deux formats, Excel transporteurs"],
      ["Chaîne incomplète", "scans oubliés, transporteurs non renseignés, colis en transit"],
      ["Aucun référentiel", "ni distances, ni facteurs, ni topologie du réseau prêts à l'emploi"]]],
  ];
  colonnes.forEach(([titre, icn, lignes], k) => {
    const x = M + k * 6.15;
    carte(s, x, 1.6, 5.9, 5.0, "colonne " + titre);
    s.addImage({ data: icn, x: x + 0.35, y: 1.85, w: 0.5, h: 0.5, objectName: "icone " + titre });
    texte(s, titre, { x: x + 1.05, y: 1.85, w: 4.5, h: 0.5, fontSize: 22, bold: true, color: C.text2, fontFace: "Cambria", valign: "middle" });
    lignes.forEach(([t, d], i) => {
      texte(s, [{ text: t, options: { bold: true, breakLine: true, color: "0B0B0B" } }, { text: d }],
            { x: x + 0.35, y: 2.65 + i * 1.3, w: 5.2, h: 1.15, fontSize: 16, valign: "top" });
    });
  });
  s.addNotes("Le cours fixe l'objectif : un dataset unifié et propre pour entraîner un modèle de CO2 à partir de données hétérogènes et incomplètes. Nous y avons ajouté la restitution client.");

  // 4. Sources ---------------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Besoin et données" });
  s.addText("Neuf sources, dont cinq référentiels publics réels", { placeholder: "title" });
  const ent = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } });
  const reel = (t) => ({ text: t, options: { bold: true, color: HEX.accent1 } });
  const fict = (t) => ({ text: t, options: { color: "8A8984" } });
  const lignesSrc = [
    [ent("Source"), ent("Format"), ent("Apport"), ent("Nature")],
    ["Export SAP", "CSV Windows-1252, « ; », virgule décimale", "commandes, poids, dimensions, service", fict("simulée")],
    ["Flashages", "12 fichiers JSON Lines, 2 firmwares", "362 199 scans : site, heure, GPS, transporteur", fict("simulée")],
    ["Annuaire transporteurs", "Excel, 2 onglets différents", "véhicule et énergie de 110 flottes", fict("simulée")],
    ["Référentiel des sites", "CSV", "129 plateformes, agences, entrepôts", fict("simulée")],
    ["Base Carbone ADEME", "CSV latin-1, 18 616 lignes", "22 facteurs fret, identifiants officiels", reel("réelle")],
    ["GeoNames", "TSV, 69 000 villes", "géocodage, population, fuseaux", reel("réelle")],
    ["OpenFlights", "CSV", "aéroports partenaires (IATA)", reel("réelle")],
    ["OSRM (OpenStreetMap)", "API", "16 512 distances routières réelles", reel("réelle")],
    ["searoute", "bibliothèque Python", "routes maritimes (Suez compris)", reel("réelle")],
  ];
  s.addTable(lignesSrc, { x: M, y: 1.55, w: W - 2 * M, colW: [2.6, 3.4, 4.3, 1.83], fontSize: 13, fontFace: "Calibri",
    color: "333333", border: { type: "solid", pt: 0.5, color: "D9DED9" }, rowH: 0.42, valign: "middle", objectName: "tableau sources" });
  texte(s, "Les sources internes sont simulées avec des défauts réalistes et une vérité terrain cachée : on peut mesurer la qualité du pipeline, ce qu'aucune donnée réelle ne permet.",
        { x: M, y: 6.35, w: W - 2 * M, h: 0.5, fontSize: 14, italic: true, color: "52514E" });
  s.addNotes("Le cours autorise des fichiers fictifs pour les données internes. Nous en avons profité pour garder la vérité terrain de côté et évaluer le pipeline. Tous les référentiels, eux, sont réels et téléchargés automatiquement.");

  // 5. Pipeline --------------------------------------------------------------------------------
  pres.addSection({ title: "Pipeline" });
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Pipeline" });
  s.addText("Sept étapes, relancées de bout en bout en 90 secondes", { placeholder: "title" });
  const etapes = [["Découverte", ic.loupe, "rapport de profilage par formes"], ["Ingestion", ic.base, "couche brute Parquet tracée"],
    ["Nettoyage", ic.balai, "Raw Clean + journal des règles"], ["Enrichis-\nsement", ic.carte, "géocodage, trajets, distances"],
    ["Features\net ML", ic.robot, "véhicules, facteurs, 3 modèles"], ["Validation", ic.check, "13 règles + vérité terrain"],
    ["Publication", ic.envoi, "Curated, Excel clients, interface"]];
  const lw = (W - 2 * M - 6 * 0.22) / 7;
  etapes.forEach(([t, icn, l], i) => {
    const x = M + i * (lw + 0.22);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.9, w: lw, h: 2.4, fill: { color: i % 2 ? HEX.accent1 : HEX.dk2 }, line: { color: i % 2 ? HEX.accent1 : HEX.dk2 }, rectRadius: 0.12, objectName: "etape " + t });
    texte(s, String(i + 1), { x: x + 0.15, y: 2.0, w: 0.5, h: 0.4, fontSize: 14, color: "C9DCD2", bold: true });
    s.addImage({ data: icn, x: x + lw / 2 - 0.3, y: 2.45, w: 0.6, h: 0.6, objectName: "icone " + t });
    texte(s, t, { x: x + 0.08, y: 3.2, w: lw - 0.16, h: 0.9, fontSize: 15, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    texte(s, l, { x, y: 4.5, w: lw, h: 0.9, fontSize: 13, color: "52514E", align: "center", valign: "top" });
  });
  carte(s, M, 5.6, W - 2 * M, 1.1, "commande", "EEF3EE");
  texte(s, [{ text: "python run_pipeline.py", options: { fontFace: "Courier New", bold: true, color: C.text2 } },
            { text: "   un module Python par étape (paquet co2), 17 tests unitaires, notebook exécuté, journal de chaque transformation", options: { color: "333333" } }],
        { x: M + 0.35, y: 5.6, w: W - 2 * M - 0.7, h: 1.1, fontSize: 15, valign: "middle" });
  s.addNotes("Les étapes reprennent exactement celles du cours. Chaque étape écrit sa couche de données : raw, raw_clean, enriched, curated. Le notebook ne contient pas de logique, il appelle les modules.");

  // 6. Découverte et nettoyage ------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Pipeline" });
  s.addText("Chaque défaut est trouvé, corrigé et journalisé", { placeholder: "title" });
  const defs = [["3 formats de date", "20260314, 14.03.2026, 2026-03-14"], ["22 libellés pour 8 clients", "AMAZON EU SARL, amazon.fr..."],
                ["1 334 poids en grammes", "déclarés en kg, divisés par 1 000"], ["2 firmwares de scanner", "epoch en ms et codes courts contre ISO 8601"],
                ["7 048 GPS inversés", "détectés par distance au site"], ["10 539 doubles flashages", "même scan à moins de 5 minutes"]];
  defs.forEach(([t, d], i) => {
    const y = 1.55 + i * 0.86;
    texte(s, [{ text: t, options: { bold: true, color: C.text2, breakLine: true } }, { text: d, options: { color: "52514E" } }],
          { x: M, y, w: 4.6, h: 0.8, fontSize: 15, valign: "top" });
  });
  image(s, fig("07_defauts"), 5.5, 1.55, 7.2, 5.2, "figure défauts");
  s.addNotes("La découverte réduit chaque valeur à sa forme : chiffres en 9, lettres en A. Plusieurs formes dans une colonne révèlent des formats concurrents. Le graphique compare les défauts injectés et ceux traités : on retrouve presque tout.");

  // 7. Reconstitution --------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Pipeline" });
  s.addText("Les scans manquants sont déduits du réseau", { placeholder: "title" });
  const chaine = [["Entrepôt\nAmiens", false], ["Tri\nLille", false], ["Tri\nLyon", true], ["Agence\nGrenoble", false], ["Client", false]];
  const bw = 1.95, gap = 0.55, x0 = (W - (5 * bw + 4 * gap)) / 2;
  chaine.forEach(([t, infere], i) => {
    const x = x0 + i * (bw + gap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.8, w: bw, h: 1.3, rectRadius: 0.12, objectName: "maillon " + i,
      fill: { color: infere ? "FFFFFF" : HEX.dk2 }, line: { color: infere ? HEX.accent2 : HEX.dk2, width: infere ? 2.5 : 1, dashType: infere ? "dash" : "solid" } });
    texte(s, t, { x, y: 1.8, w: bw, h: 1.3, fontSize: 16, bold: true, align: "center", valign: "middle", color: infere ? HEX.accent2 : "FFFFFF" });
    if (i < 4) s.addShape(pres.shapes.LINE, { x: x + bw + 0.08, y: 2.45, w: gap - 0.16, h: 0, line: { color: "8A8984", width: 2, endArrowType: "triangle" }, objectName: "fleche " + i });
  });
  texte(s, "scan manquant : plateforme déduite", { x: x0 + 2 * (bw + gap) - 0.3, y: 3.2, w: bw + 0.6, h: 0.4, fontSize: 13, color: HEX.accent2, align: "center", italic: true });
  const faits = [["117", "rattachements agence ou entrepôt → plateforme appris dans les scans (vote majoritaire)"],
                 ["15,8 %", "des colis ont au moins une étape déduite, sans perte de précision notable"],
                 ["98,5 %", "de bonnes prédictions du mode (avion, bateau, route) quand la porte d'entrée n'est pas flashée, contre 87,4 % pour la règle par pays"]];
  faits.forEach(([v, l], i) => {
    const x = M + i * 4.1;
    carte(s, x, 4.1, 3.85, 2.55, "fait " + i, "EEF3EE");
    texte(s, v, { x: x + 0.3, y: 4.3, w: 3.3, h: 0.8, fontSize: 34, bold: true, color: C.accent1, fontFace: "Cambria" });
    texte(s, l, { x: x + 0.3, y: 5.15, w: 3.3, h: 1.4, fontSize: 14, valign: "top" });
  });
  s.addNotes("Le pipeline n'a pas de carte du réseau : il l'apprend. Pour chaque agence, la plateforme scannée juste avant son arrivée la plus souvent. Quand un scan manque, on réinsère la plateforme attendue. Pour un colis d'Asie sans scan d'entrée, le délai entre commande et premier scan trahit l'avion ou le bateau.");

  // 8. Distances et facteurs --------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Pipeline" });
  s.addText("Distances réelles par mode, facteurs officiels de l'ADEME", { placeholder: "title" });
  const meth = [[ic.camion, "Route", "distance OSRM réelle entre sites ; sinon vol d'oiseau × 1,27, calibré sur 16 512 trajets"],
                [ic.avion, "Avion", "orthodromie + 95 km (norme EN 16258), facteur selon la distance, traînées incluses"],
                [ic.bateau, "Bateau", "route maritime réelle (searoute), facteur de la ligne Asie-Europe"],
                [ic.velo, "Dernier km", "tournée : distance × 1,6 ; −40 % en point relais"]];
  meth.forEach(([icn, t, d], i) => {
    const y = 1.6 + i * 1.25;
    s.addImage({ data: icn, x: M, y: y + 0.1, w: 0.55, h: 0.55, objectName: "icone " + t });
    texte(s, [{ text: t, options: { bold: true, color: C.text2, breakLine: true } }, { text: d }], { x: M + 0.8, y, w: 4.9, h: 1.15, fontSize: 14, valign: "top" });
  });
  const fac = [["Avion cargo > 5 000 km", 1010], ["Utilitaire gazole", 842], ["Porteur 12 à 20 t", 169], ["Utilitaire électrique", 121.8],
               ["Articulé 40 t gazole", 87.5], ["Porte-conteneur Asie-Europe", 5.5], ["Train électrique", 4.6]];
  s.addChart(pres.charts.BAR, [{ name: "g CO₂e par tonne.km", labels: fac.map((f) => f[0]), values: fac.map((f) => f[1]) }], {
    x: 6.6, y: 1.5, w: 6.1, h: 5.2, barDir: "bar", catAxisOrientation: "maxMin", valAxisLogScaleBase: 10,
    chartColors: [HEX.accent2, HEX.accent4, HEX.accent3, HEX.accent4, HEX.accent3, HEX.accent5, "E87BA4"],
    showTitle: true, title: "Facteurs ADEME (g CO₂e par tonne.km, échelle log)", titleFontSize: 14, titleColor: "333333", titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: "333333", dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
    catAxisLabelColor: "52514E", catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt", valAxisHidden: true,
    valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, barGapWidthPct: 45, objectName: "graphique facteurs",
  });
  s.addNotes("Les 22 facteurs sont extraits de la Base Carbone par leur identifiant, jamais recopiés à la main. Deux sont dérivés : l'utilitaire électrique et le vélo cargo. Entre le train et l'avion, il y a un facteur 200.");

  // 9. ML ----------------------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Pipeline" });
  s.addText("Trois modèles, chacun comparé à une règle simple", { placeholder: "title" });
  const mm = resume.metriques_modeles;
  const k = Object.keys(mm);
  const tab = [[ent("Question"), ent("Utilisé pour"), ent("Règle simple"), ent("Modèle")],
    ["Avion, bateau ou route ?", "colis étrangers sans scan d'entrée", `${fr(100 * mm[k[0]].precision_regle_pays, 1)} % (mode du pays)`, reel(`${fr(100 * mm[k[0]].precision_modele, 1)} % de bonnes réponses`)],
    ["Quel véhicule ?", "étapes sans transporteur (70 % des colis)", `${fr(100 * mm[k[1]].precision_regle_frequence, 1)} % (le plus fréquent)`, reel(`${fr(100 * mm[k[1]].precision_modele, 1)} % + facteur moyen pondéré`)],
    ["Combien de CO₂ avant l'envoi ?", "calculateur, contrôle des anomalies", `${fr(mm[k[2]].erreur_absolue_mediane_pct_naif, 1)} % d'erreur médiane`, reel(`${fr(mm[k[2]].erreur_absolue_mediane_pct, 1)} %, intervalle à 80 % tenu à ${fr(100 * mm[k[2]].couverture_intervalle_80)} %`)]];
  s.addTable(tab, { x: M, y: 1.6, w: W - 2 * M, colW: [3.0, 3.4, 2.7, 3.03], fontSize: 15, fontFace: "Calibri", color: "333333",
    border: { type: "solid", pt: 0.5, color: "D9DED9" }, rowH: 0.75, valign: "middle", objectName: "tableau modèles" });
  carte(s, M, 4.95, W - 2 * M, 1.7, "lecture", "EEF3EE");
  texte(s, [{ text: "Ce qu'on en retient", options: { bold: true, color: C.text2, breakLine: true } },
    { text: "Le véhicule exact est peu prévisible : le modèle gagne un point seulement. Mais en pondérant les facteurs par ses probabilités au lieu de prendre la classe la plus probable, le biais sur le total de l'option écologique passe de −6 % à −0,8 %. Les intervalles sont calibrés par régression quantile conformalisée.", options: {} }],
    { x: M + 0.35, y: 5.05, w: W - 2 * M - 0.7, h: 1.5, fontSize: 15, valign: "top" });
  s.addNotes("Gradient boosting (HistGradientBoosting de scikit-learn) pour les trois. Nous présentons honnêtement le cas où le modèle apporte peu, et ce que nous avons fait à la place.");

  // 10. Validation ------------------------------------------------------------------------------
  pres.addSection({ title: "Résultats" });
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Résultats" });
  s.addText(`${fr(ev.emission_reconstituee.erreur_mediane_pct, 1)} % d'erreur médiane face à la vérité terrain`, { placeholder: "title" });
  image(s, fig("05_estime_vs_reel"), M, 1.5, 4.9, 5.2, "nuage estimé contre réel");
  image(s, fig("04_erreur_par_observation"), 5.8, 1.5, 6.9, 4.4, "erreur par part observée");
  texte(s, `Biais sur le total de l'année : ${fr(ev.emission_reconstituee.biais_total_pct, 2)} %. ${fr(ev.emission_reconstituee.part_a_moins_de_20pct, 1)} % des colis à moins de 20 % près. 13 règles de cohérence : 11 OK, 2 alertes sous 1 %.`,
        { x: 5.8, y: 6.0, w: 6.9, h: 0.75, fontSize: 14, color: "333333" });
  s.addNotes("Même quand moins de la moitié du trajet est observée, la reconstitution reste à 4 % d'erreur médiane. Le modèle sur la commande seule est moins précis, c'est attendu : il ne voit aucun scan.");

  // 11. Clients ---------------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Résultats" });
  s.addText("Shein et Amazon concentrent 85 % des émissions", { placeholder: "title" });
  const cl = [["Shein", 24.55], ["Amazon", 17.52], ["Cdiscount", 3.66], ["Vinted", 1.27], ["Leroy Merlin", 1.19], ["Decathlon", 0.92], ["Zalando", 0.42], ["Back Market", 0.17]];
  s.addChart(pres.charts.BAR, [{ name: "t CO₂e", labels: cl.map((c) => c[0]), values: cl.map((c) => c[1]) }], {
    x: M, y: 1.5, w: 7.0, h: 5.2, barDir: "bar", catAxisOrientation: "maxMin", chartColors: [HEX.accent1],
    showTitle: true, title: "Émissions sur 12 mois (t CO₂e)", titleFontSize: 14, titleColor: "333333", titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: "333333", dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
    catAxisLabelColor: "52514E", catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", valAxisHidden: true,
    valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, barGapWidthPct: 40, objectName: "graphique clients",
  });
  const lec = [["Shein", "10 % des colis, 49 % des émissions : 99 % par avion, 4 kg par colis"],
               ["Amazon", "le colis médian émet 75 g, mais environ 8 % d'imports font 87 % du total"],
               ["Vinted", "13 142 colis entre particuliers pour 1,3 t : 96 g par colis, point relais majoritaire"]];
  lec.forEach(([t, d], i) => {
    carte(s, 8.0, 1.6 + i * 1.75, 4.73, 1.55, "lecture " + t, "EEF3EE");
    texte(s, [{ text: t, options: { bold: true, color: C.text2, breakLine: true } }, { text: d }], { x: 8.3, y: 1.75 + i * 1.75, w: 4.2, h: 1.3, fontSize: 15, valign: "top" });
  });
  s.addNotes("Le classement suit l'exposition au transport aérien, pas le volume de colis : Vinted expédie deux fois plus de colis que Shein pour vingt fois moins de CO2.");

  // 12. Leviers ---------------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Résultats" });
  s.addText("Un kilo d'Asie : 8,6 kg CO₂e en avion, 182 g en bateau", { placeholder: "title" });
  const kg = [["International par avion", 8641], ["International par bateau", 182], ["Standard", 92], ["Express", 85], ["Écologique", 54]];
  s.addChart(pres.charts.BAR, [{ name: "g CO₂e par kg", labels: kg.map((c) => c[0]), values: kg.map((c) => c[1]) }], {
    x: M, y: 1.5, w: 7.0, h: 5.2, barDir: "bar", catAxisOrientation: "maxMin", valAxisLogScaleBase: 10,
    chartColors: [HEX.accent2, HEX.accent5, HEX.accent3, HEX.accent6, HEX.accent4],
    showTitle: true, title: "g CO₂e par kilo expédié (échelle log)", titleFontSize: 14, titleColor: "333333", titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: "333333", dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "#,##0",
    catAxisLabelColor: "52514E", catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", valAxisHidden: true,
    valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, barGapWidthPct: 40, objectName: "graphique par kilo",
  });
  const lev = [["× 47", "l'écart entre avion et bateau pour un même kilo"], ["− 41 %", "l'option écologique face au standard (train, électrique, vélo cargo)"],
               ["≈ 0", "l'écart entre express et standard sur le territoire : l'express roule en ligne directe"]];
  lev.forEach(([v, d], i) => {
    carte(s, 8.0, 1.6 + i * 1.75, 4.73, 1.55, "levier " + i, "EEF3EE");
    texte(s, v, { x: 8.3, y: 1.7 + i * 1.75, w: 1.6, h: 1.35, fontSize: 30, bold: true, color: C.accent1, fontFace: "Cambria", valign: "middle" });
    texte(s, d, { x: 9.95, y: 1.7 + i * 1.75, w: 2.6, h: 1.35, fontSize: 14, valign: "middle" });
  });
  s.addNotes("Ce sont les leviers que l'interface permet de simuler sur le bilan de chaque client. Le résultat sur l'express est contre-intuitif mais cohérent avec les données : pas de détour par le hub national.");

  // 13. Interface --------------------------------------------------------------------------------
  pres.addSection({ title: "Interface et organisation" });
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Interface et organisation" });
  s.addText("Une interface pensée pour un client non technique", { placeholder: "title" });
  image(s, rogne("app_calcul_resultat"), M, 1.5, 5.95, 4.05, "capture calculateur");
  image(s, rogne("app_bilan"), 6.78, 1.5, 5.95, 4.05, "capture bilan");
  const pages = [["Calculer un envoi", "départ, arrivée, poids : l'empreinte, le trajet, les autres options"],
                 ["Mon bilan carbone", "mois par mois, par mode, leviers simulés, export Excel"],
                 ["Comment c'est calculé", "la méthode en clair, les facteurs ADEME et les limites"]];
  pages.forEach(([t, d], i) => {
    texte(s, [{ text: t, options: { bold: true, color: C.text2, breakLine: true } }, { text: d }], { x: M + i * 4.1, y: 5.75, w: 3.85, h: 1.0, fontSize: 14, valign: "top" });
  });
  s.addNotes("Démonstration : python run_app.py. Pas de jargon : des grammes, des équivalents en kilomètres de voiture, une phrase qui recommande l'option la plus sobre.");

  // 14. Gestion de projet ---------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "CONTENU", sectionTitle: "Interface et organisation" });
  s.addText("Organisation Scrum : 4 epics, 3 sprints de deux semaines", { placeholder: "title" });
  const ep = [[ent("Epic"), ent("Exemple de user story"), ent("Sprint")],
    ["1. Ingestion des sources", "En tant que data engineer, je veux charger SAP, scans et transporteurs dans un format unique", "1"],
    ["2. Qualité et nettoyage", "En tant que data steward, je veux un journal de chaque correction appliquée", "1"],
    ["3. Calcul et modèles", "En tant que data scientist, je veux estimer le véhicule quand le transporteur manque", "2"],
    ["4. Restitution client", "En tant que responsable RSE d'un client, je veux mon bilan CO₂ mensuel en Excel", "3"]];
  s.addTable(ep, { x: M, y: 1.55, w: 8.2, colW: [2.5, 4.9, 0.8], fontSize: 13, fontFace: "Calibri", color: "333333",
    border: { type: "solid", pt: 0.5, color: "D9DED9" }, rowH: 0.8, valign: "middle", objectName: "tableau epics" });
  s.addImage({ data: ic.users, x: 9.2, y: 1.6, w: 0.5, h: 0.5, objectName: "icone équipe" });
  texte(s, "L'équipe", { x: 9.85, y: 1.6, w: 3, h: 0.5, fontSize: 20, bold: true, color: C.text2, fontFace: "Cambria", valign: "middle" });
  const roles = [["Kheireddine BOUADI", "Product Owner, data engineer"], ["Maël RAZAFIMBELO", "Scrum Master, validation"],
                 ["Mohamed BEN AMOR", "Data engineer, nettoyage"], ["Ael Boece NGODA LONTSI", "Data scientist, modèles"],
                 ["Abdallah BENSMAIL", "Data analyst, interface"]];
  roles.forEach(([n, r], i) => texte(s, [{ text: n, options: { bold: true, breakLine: true } }, { text: r, options: { color: "52514E" } }],
    { x: 9.2, y: 2.3 + i * 0.85, w: 3.6, h: 0.8, fontSize: 14, valign: "top" }));
  texte(s, "Definition of Done : code testé, étape journalisée, règle de validation verte, documentation à jour.",
        { x: M, y: 5.85, w: 8.2, h: 0.7, fontSize: 14, italic: true, color: "52514E" });
  s.addNotes("Backlog complet, sprint 1 détaillé et tableau Kanban dans docs/gestion_projet.md.");

  // 15. Conclusion -------------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "TITRE_SOMBRE", sectionTitle: "Interface et organisation" });
  s.addText("Limites et prochaines étapes", { placeholder: "title" });
  s.addText([
    { text: "Brancher les vraies extractions SAP et scanners : le pipeline ne dépend que du format", options: { bullet: true, breakLine: true } },
    { text: "Ajouter les émissions des plateformes et le trajet du client vers le point relais", options: { bullet: true, breakLine: true } },
    { text: "Remplacer le coefficient de tournée par les vraies tournées (GPS des véhicules)", options: { bullet: true, breakLine: true } },
    { text: "Exposer le calculateur en API pour l'afficher au moment de la commande", options: { bullet: true } },
  ], { placeholder: "body", paraSpaceAfter: 8, fontSize: 18 });
  s.addNotes("Merci. Le code, les données, le notebook et la documentation sont sur le dépôt GitHub indiqué dans le mail.");

  const out = path.join(RACINE, "presentation/presentation_co2.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("écrit :", out);
})();
