"use strict";

// Page text in English, Danish, German and French. English is the fallback for any missing key.
// Placeholders look like {name}. Server error messages stay English in the API; the page shows
// its own text for each error `code`, below.
const STRINGS = { en: {}, da: {}, de: {}, fr: {} };
const LOCALES = { en: "en-GB", da: "da-DK", de: "de-DE", fr: "fr-FR" };
const LANGUAGE_NAMES = { en: "English", da: "Dansk", de: "Deutsch", fr: "Français" };

STRINGS.en = {
  page_title: "watt-brief: when is power cheap?",
  page_description:
    "Day-ahead electricity prices for European markets, with a plain answer on when to run your heat pump, charger or washing machine.",
  source_link: "Source and evals",
  country: "Country",
  country_placeholder: "Type to filter",
  countries: "Countries",
  combo_empty: "No matching country",
  clear_hint: "Clear the country field to let your question choose the country.",
  unit: "Unit",
  currency: "Currency",
  language: "Language",
  loading_context: "Loading prices.",
  loading_answer: "Checking today's prices.",
  per: " per ",
  hour_one: "{n} hour",
  hour_other: "{n} hours",
  chart_title: "Day-ahead price in {basis}, by hour in UTC",
  chart_aria_default:
    "Price chart. Use the left and right arrow keys to read each hour.",
  plot_aria:
    "Price chart for {zone}. Cheapest {hours} are {from} to {to} UTC. Use the left and right arrow keys to read each hour.",
  table_caption: "Day-ahead prices in {basis}",
  col_utc: "Time (UTC)",
  col_local: "Your time ({zone})",
  col_price: "Price ({label})",
  col_note: "Note",
  note_cheap: "Cheapest window",
  note_pricey: "Priciest window",
  tip_cheap: "In the cheapest window",
  tip_pricey: "In the priciest window",
  key_cheap: "Cheapest {hours}",
  key_pricey: "Priciest {hours}",
  show_table: "Show as table",
  show_chart: "Show as chart",
  source_synthetic: "Synthetic demo data, not market prices.",
  source_real: "Day-ahead prices from ENTSO-E.",
  source_real_fetched: "Day-ahead prices from ENTSO-E, fetched {time} UTC.",
  versus_cheaper: "On average {pct}% cheaper than the day before.",
  versus_dearer: "On average {pct}% dearer than the day before.",
  answer: "Power is cheapest between {from} and {to} UTC.",
  detail_local: "That is {from} to {to} in {zone}.",
  detail_average: "It averages {avg} {label}, against {mean} over the whole day.",
  detail_avoid: "Avoid {from} to {to} UTC, which averages {avg}.",
  basis_kwh: "{words}, converted from EUR per MWh (1 MWh = 1000 kWh)",
  basis_fx: "{words}, converted from EUR per MWh at the fixed rate 1 EUR = {rate} DKK",
  foot_note:
    "Prices are day-ahead, in {basis}. Times are UTC unless a time zone is named. Guidance only, not financial advice.",
  foot_links: "How it works, the decisions behind it, and the eval results",
  privacy: "Privacy",
  fx_note: "1 EUR = {rate} DKK, the fixed central rate the krone is pegged to.",
  prices_unavailable: "Prices are not available right now.",
  prices_unavailable_detail:
    "The price service did not answer. You can still ask a question below, or try again in a minute.",
  ask_title: "Ask about your own situation",
  ask_lead:
    "Tell us what you need to run and for how long. You get a short brief that ends in a decision.",
  your_question: "Your question",
  question_placeholder: "I need 3 hours for my heat pump tomorrow. When should it run?",
  get_brief: "Get my brief",
  working: "Working",
  count: "{n} of {max}",
  or_try: "Or try:",
  chip1: "heat pump, 3 hours",
  chip1_q: "I need 3 hours of power tomorrow. When should I run my heat pump?",
  chip2: "the expensive hours",
  chip2_q: "When is electricity most expensive tomorrow, so I can avoid it?",
  chip3: "negative prices",
  chip3_q: "Are there negative prices tomorrow, and when?",
  why: "Why",
  caveats: "Caveats",
  meta:
    "Based on {source} for {zone} ({basis}), a {hours}-hour window, times in UTC. Figures in the written brief are in {unit}{prices}. Reference {id}.",
  meta_source_synthetic: "synthetic demo data",
  meta_source_real: "ENTSO-E day-ahead prices",
  meta_basis_selector: "the country you chose",
  meta_basis_question: "the country named in your question",
  meta_basis_default: "the default country, as none was chosen or named",
  meta_prices: "; the chart is in {basis}",
  empty_question: "Type a question first.",
  network_error: "Could not reach the service. Check your connection and try again.",
  err_killed: "The service is paused. Try again later.",
  err_banned: "Too many requests. Try again later.",
  err_rate_limited: "Too many requests. Try again later.",
  err_budget: "Today's budget is used up. Try again tomorrow (UTC).",
  err_busy: "The service is busy. Try again in a moment.",
  err_bad_request: "That request could not be read. Reload the page and try again.",
  err_too_large: "That request is too large.",
  err_bad_type: "That request could not be read. Reload the page and try again.",
  err_bad_query: "That choice is not available.",
  err_error: "Something went wrong. Try again later.",
  err_model_error: "I couldn't produce a brief right now. Try again later.",
  err_empty: "Ask a question about European day-ahead electricity prices.",
  err_too_long: "Keep the question under 500 characters.",
  err_delimiter: "That question contains text I can't accept.",
  err_off_topic: "I only answer questions about electricity prices and when to use power.",
  err_unsafe_output: "I couldn't produce a safe answer. Try rephrasing the question.",
  err_no_data: "Price data is not available right now.",
  err_no_prices: "Price data is not available right now.",
  err_zone_unknown: "I don't have price data for that country yet.",
  err_zone_unsupported: "I don't cover that country yet. Choose one from the country list.",
  err_denmark_ambiguous:
    "Denmark has two price zones: DK1 (Jutland and Funen) and DK2 (Zealand and Copenhagen). Choose one in the country list, or name a Danish city in your question.",
};

STRINGS.da = {
  page_title: "watt-brief: hvornår er strømmen billig?",
  page_description:
    "Day-ahead-elpriser for europæiske markeder med et klart svar på, hvornår du bør køre varmepumpen, laderen eller vaskemaskinen.",
  source_link: "Kildekode og evalueringer",
  country: "Land",
  country_placeholder: "Skriv for at filtrere",
  countries: "Lande",
  combo_empty: "Intet land passer",
  clear_hint: "Ryd landefeltet, så dit spørgsmål vælger landet.",
  unit: "Enhed",
  currency: "Valuta",
  language: "Sprog",
  loading_context: "Henter priser.",
  loading_answer: "Tjekker dagens priser.",
  per: " pr. ",
  hour_one: "{n} time",
  hour_other: "{n} timer",
  chart_title: "Day-ahead-pris i {basis}, pr. time i UTC",
  chart_aria_default: "Prisdiagram. Brug venstre og højre piletast til at læse hver time.",
  plot_aria:
    "Prisdiagram for {zone}. De billigste {hours} er {from} til {to} UTC. Brug venstre og højre piletast til at læse hver time.",
  table_caption: "Day-ahead-priser i {basis}",
  col_utc: "Tid (UTC)",
  col_local: "Din tid ({zone})",
  col_price: "Pris ({label})",
  col_note: "Note",
  note_cheap: "Billigste vindue",
  note_pricey: "Dyreste vindue",
  tip_cheap: "I det billigste vindue",
  tip_pricey: "I det dyreste vindue",
  key_cheap: "Billigste {hours}",
  key_pricey: "Dyreste {hours}",
  show_table: "Vis som tabel",
  show_chart: "Vis som diagram",
  source_synthetic: "Syntetiske demodata, ikke markedspriser.",
  source_real: "Day-ahead-priser fra ENTSO-E.",
  source_real_fetched: "Day-ahead-priser fra ENTSO-E, hentet {time} UTC.",
  versus_cheaper: "I gennemsnit {pct} % billigere end dagen før.",
  versus_dearer: "I gennemsnit {pct} % dyrere end dagen før.",
  answer: "Strømmen er billigst mellem {from} og {to} UTC.",
  detail_local: "Det er {from} til {to} i {zone}.",
  detail_average: "Gennemsnit {avg} {label} mod {mean} over hele dagen.",
  detail_avoid: "Undgå {from} til {to} UTC, med et gennemsnit på {avg}.",
  basis_kwh: "{words}, omregnet fra EUR pr. MWh (1 MWh = 1000 kWh)",
  basis_fx: "{words}, omregnet fra EUR pr. MWh til den faste kurs 1 EUR = {rate} DKK",
  foot_note:
    "Priserne er day-ahead, i {basis}. Tider er i UTC, medmindre en tidszone er nævnt. Kun vejledning, ikke økonomisk rådgivning.",
  foot_links: "Sådan virker det, begrundelserne bag og evalueringsresultaterne",
  privacy: "Privatliv",
  fx_note: "1 EUR = {rate} DKK, den faste centralkurs, som kronen er knyttet til.",
  prices_unavailable: "Priserne er ikke tilgængelige lige nu.",
  prices_unavailable_detail:
    "Prisservicen svarede ikke. Du kan stadig stille et spørgsmål nedenfor eller prøve igen om lidt.",
  ask_title: "Spørg om din egen situation",
  ask_lead:
    "Fortæl, hvad du skal bruge strøm til, og hvor længe. Du får et kort notat, der ender i en beslutning.",
  your_question: "Dit spørgsmål",
  question_placeholder: "Jeg skal bruge 3 timer til min varmepumpe i morgen. Hvornår skal den køre?",
  get_brief: "Få mit notat",
  working: "Arbejder",
  count: "{n} af {max}",
  or_try: "Eller prøv:",
  chip1: "varmepumpe, 3 timer",
  chip1_q: "Jeg skal bruge 3 timers strøm i morgen. Hvornår skal varmepumpen køre?",
  chip2: "de dyre timer",
  chip2_q: "Hvornår er strømmen dyrest i morgen, så jeg kan undgå det?",
  chip3: "negative priser",
  chip3_q: "Er der negative priser i morgen, og hvornår?",
  why: "Hvorfor",
  caveats: "Forbehold",
  meta:
    "Baseret på {source} for {zone} ({basis}), et {hours}-timers vindue, tider i UTC. Tallene i notatet er i {unit}{prices}. Reference {id}.",
  meta_source_synthetic: "syntetiske demodata",
  meta_source_real: "ENTSO-E day-ahead-priser",
  meta_basis_selector: "det land, du valgte",
  meta_basis_question: "det land, der nævnes i dit spørgsmål",
  meta_basis_default: "standardlandet, da intet land blev valgt eller nævnt",
  meta_prices: "; diagrammet er i {basis}",
  empty_question: "Skriv et spørgsmål først.",
  network_error: "Kunne ikke nå tjenesten. Tjek din forbindelse og prøv igen.",
  err_killed: "Tjenesten er sat på pause. Prøv igen senere.",
  err_banned: "For mange forespørgsler. Prøv igen senere.",
  err_rate_limited: "For mange forespørgsler. Prøv igen senere.",
  err_budget: "Dagens budget er brugt. Prøv igen i morgen (UTC).",
  err_busy: "Tjenesten er optaget. Prøv igen om et øjeblik.",
  err_bad_request: "Forespørgslen kunne ikke læses. Genindlæs siden og prøv igen.",
  err_too_large: "Forespørgslen er for stor.",
  err_bad_type: "Forespørgslen kunne ikke læses. Genindlæs siden og prøv igen.",
  err_bad_query: "Det valg er ikke tilgængeligt.",
  err_error: "Noget gik galt. Prøv igen senere.",
  err_model_error: "Jeg kunne ikke lave et notat lige nu. Prøv igen senere.",
  err_empty: "Stil et spørgsmål om europæiske day-ahead-elpriser.",
  err_too_long: "Hold spørgsmålet under 500 tegn.",
  err_delimiter: "Spørgsmålet indeholder tekst, jeg ikke kan acceptere.",
  err_off_topic: "Jeg svarer kun på spørgsmål om elpriser og om, hvornår man bør bruge strøm.",
  err_unsafe_output: "Jeg kunne ikke lave et sikkert svar. Prøv at omformulere spørgsmålet.",
  err_no_data: "Prisdata er ikke tilgængelige lige nu.",
  err_no_prices: "Prisdata er ikke tilgængelige lige nu.",
  err_zone_unknown: "Jeg har ikke prisdata for det land endnu.",
  err_zone_unsupported: "Jeg dækker ikke det land endnu. Vælg et fra landelisten.",
  err_denmark_ambiguous:
    "Danmark har to prisområder: DK1 (Jylland og Fyn) og DK2 (Sjælland og København). Vælg et på landelisten, eller nævn en dansk by i dit spørgsmål.",
};

STRINGS.de = {
  page_title: "watt-brief: Wann ist Strom günstig?",
  page_description:
    "Day-Ahead-Strompreise für europäische Märkte, mit einer klaren Antwort, wann Wärmepumpe, Ladegerät oder Waschmaschine laufen sollten.",
  source_link: "Quellcode und Auswertungen",
  country: "Land",
  country_placeholder: "Zum Filtern tippen",
  countries: "Länder",
  combo_empty: "Kein passendes Land",
  clear_hint: "Leere das Länderfeld, damit deine Frage das Land bestimmt.",
  unit: "Einheit",
  currency: "Währung",
  language: "Sprache",
  loading_context: "Preise werden geladen.",
  loading_answer: "Die heutigen Preise werden geprüft.",
  per: " pro ",
  hour_one: "{n} Stunde",
  hour_other: "{n} Stunden",
  chart_title: "Day-Ahead-Preis in {basis}, je Stunde in UTC",
  chart_aria_default:
    "Preisdiagramm. Mit den Pfeiltasten links und rechts liest du jede Stunde.",
  plot_aria:
    "Preisdiagramm für {zone}. Die günstigsten {hours} sind {from} bis {to} UTC. Mit den Pfeiltasten links und rechts liest du jede Stunde.",
  table_caption: "Day-Ahead-Preise in {basis}",
  col_utc: "Zeit (UTC)",
  col_local: "Deine Zeit ({zone})",
  col_price: "Preis ({label})",
  col_note: "Hinweis",
  note_cheap: "Günstigstes Fenster",
  note_pricey: "Teuerstes Fenster",
  tip_cheap: "Im günstigsten Fenster",
  tip_pricey: "Im teuersten Fenster",
  key_cheap: "Günstigste {hours}",
  key_pricey: "Teuerste {hours}",
  show_table: "Als Tabelle anzeigen",
  show_chart: "Als Diagramm anzeigen",
  source_synthetic: "Synthetische Demodaten, keine Marktpreise.",
  source_real: "Day-Ahead-Preise von ENTSO-E.",
  source_real_fetched: "Day-Ahead-Preise von ENTSO-E, abgerufen um {time} UTC.",
  versus_cheaper: "Im Schnitt {pct} % günstiger als am Vortag.",
  versus_dearer: "Im Schnitt {pct} % teurer als am Vortag.",
  answer: "Strom ist zwischen {from} und {to} UTC am günstigsten.",
  detail_local: "Das sind {from} bis {to} in {zone}.",
  detail_average: "Im Schnitt {avg} {label}, gegenüber {mean} über den ganzen Tag.",
  detail_avoid: "Meide {from} bis {to} UTC, im Schnitt {avg}.",
  basis_kwh: "{words}, umgerechnet aus EUR pro MWh (1 MWh = 1000 kWh)",
  basis_fx: "{words}, umgerechnet aus EUR pro MWh zum festen Kurs 1 EUR = {rate} DKK",
  foot_note:
    "Die Preise sind Day-Ahead, in {basis}. Zeiten sind UTC, sofern keine Zeitzone genannt ist. Nur zur Orientierung, keine Finanzberatung.",
  foot_links: "Wie es funktioniert, die Entscheidungen dahinter und die Testergebnisse",
  privacy: "Datenschutz",
  fx_note: "1 EUR = {rate} DKK, der feste Leitkurs, an den die Krone gebunden ist.",
  prices_unavailable: "Die Preise sind gerade nicht verfügbar.",
  prices_unavailable_detail:
    "Der Preisdienst hat nicht geantwortet. Du kannst unten trotzdem eine Frage stellen oder es in einer Minute erneut versuchen.",
  ask_title: "Frag zu deiner eigenen Situation",
  ask_lead:
    "Sag uns, was du betreiben willst und wie lange. Du erhältst eine kurze Auskunft, die in einer Entscheidung endet.",
  your_question: "Deine Frage",
  question_placeholder:
    "Ich brauche morgen 3 Stunden für meine Wärmepumpe. Wann soll sie laufen?",
  get_brief: "Auskunft holen",
  working: "Wird erstellt",
  count: "{n} von {max}",
  or_try: "Oder probiere:",
  chip1: "Wärmepumpe, 3 Stunden",
  chip1_q: "Ich brauche morgen 3 Stunden Strom für meine Wärmepumpe. Wann soll sie laufen?",
  chip2: "die teuren Stunden",
  chip2_q: "Wann ist der Strom morgen am teuersten, damit ich ihn vermeiden kann?",
  chip3: "negative Preise",
  chip3_q: "Gibt es morgen negative Strompreise, und wann?",
  why: "Warum",
  caveats: "Einschränkungen",
  meta:
    "Basierend auf {source} für {zone} ({basis}), ein {hours}-Stunden-Fenster, Zeiten in UTC. Die Zahlen in der Auskunft sind in {unit}{prices}. Referenz {id}.",
  meta_source_synthetic: "synthetischen Demodaten",
  meta_source_real: "ENTSO-E-Day-Ahead-Preisen",
  meta_basis_selector: "das von dir gewählte Land",
  meta_basis_question: "das in deiner Frage genannte Land",
  meta_basis_default: "das Standardland, da keines gewählt oder genannt wurde",
  meta_prices: "; das Diagramm ist in {basis}",
  empty_question: "Gib zuerst eine Frage ein.",
  network_error: "Der Dienst ist nicht erreichbar. Prüfe deine Verbindung und versuche es erneut.",
  err_killed: "Der Dienst ist pausiert. Versuche es später erneut.",
  err_banned: "Zu viele Anfragen. Versuche es später erneut.",
  err_rate_limited: "Zu viele Anfragen. Versuche es später erneut.",
  err_budget: "Das heutige Budget ist aufgebraucht. Versuche es morgen erneut (UTC).",
  err_busy: "Der Dienst ist ausgelastet. Versuche es gleich noch einmal.",
  err_bad_request: "Die Anfrage konnte nicht gelesen werden. Lade die Seite neu und versuche es erneut.",
  err_too_large: "Die Anfrage ist zu groß.",
  err_bad_type: "Die Anfrage konnte nicht gelesen werden. Lade die Seite neu und versuche es erneut.",
  err_bad_query: "Diese Auswahl ist nicht verfügbar.",
  err_error: "Etwas ist schiefgelaufen. Versuche es später erneut.",
  err_model_error: "Ich konnte gerade keine Auskunft erstellen. Versuche es später erneut.",
  err_empty: "Stelle eine Frage zu europäischen Day-Ahead-Strompreisen.",
  err_too_long: "Halte die Frage unter 500 Zeichen.",
  err_delimiter: "Die Frage enthält Text, den ich nicht annehmen kann.",
  err_off_topic:
    "Ich beantworte nur Fragen zu Strompreisen und dazu, wann man Strom nutzen sollte.",
  err_unsafe_output:
    "Ich konnte keine sichere Antwort erstellen. Formuliere die Frage bitte um.",
  err_no_data: "Preisdaten sind gerade nicht verfügbar.",
  err_no_prices: "Preisdaten sind gerade nicht verfügbar.",
  err_zone_unknown: "Für dieses Land habe ich noch keine Preisdaten.",
  err_zone_unsupported: "Dieses Land deckt der Dienst noch nicht ab. Wähle eines aus der Länderliste.",
  err_denmark_ambiguous:
    "Dänemark hat zwei Preiszonen: DK1 (Jütland und Fünen) und DK2 (Seeland und Kopenhagen). Wähle eine in der Länderliste oder nenne in deiner Frage eine dänische Stadt.",
};

STRINGS.fr = {
  page_title: "watt-brief : quand l'électricité est-elle bon marché ?",
  page_description:
    "Prix day-ahead de l'électricité pour les marchés européens, avec une réponse claire sur le moment de lancer pompe à chaleur, chargeur ou lave-linge.",
  source_link: "Code source et évaluations",
  country: "Pays",
  country_placeholder: "Saisir pour filtrer",
  countries: "Pays",
  combo_empty: "Aucun pays correspondant",
  clear_hint: "Videz le champ du pays pour que votre question choisisse le pays.",
  unit: "Unité",
  currency: "Devise",
  language: "Langue",
  loading_context: "Chargement des prix.",
  loading_answer: "Vérification des prix du jour.",
  per: " par ",
  hour_one: "{n} heure",
  hour_other: "{n} heures",
  chart_title: "Prix day-ahead en {basis}, par heure en UTC",
  chart_aria_default:
    "Graphique des prix. Utilisez les flèches gauche et droite pour lire chaque heure.",
  plot_aria:
    "Graphique des prix pour {zone}. Les {hours} les moins chères sont de {from} à {to} UTC. Utilisez les flèches gauche et droite pour lire chaque heure.",
  table_caption: "Prix day-ahead en {basis}",
  col_utc: "Heure (UTC)",
  col_local: "Votre heure ({zone})",
  col_price: "Prix ({label})",
  col_note: "Remarque",
  note_cheap: "Créneau le moins cher",
  note_pricey: "Créneau le plus cher",
  tip_cheap: "Dans le créneau le moins cher",
  tip_pricey: "Dans le créneau le plus cher",
  key_cheap: "{hours} les moins chères",
  key_pricey: "{hours} les plus chères",
  show_table: "Afficher en tableau",
  show_chart: "Afficher en graphique",
  source_synthetic: "Données de démonstration synthétiques, pas des prix de marché.",
  source_real: "Prix day-ahead d'ENTSO-E.",
  source_real_fetched: "Prix day-ahead d'ENTSO-E, récupérés à {time} UTC.",
  versus_cheaper: "En moyenne {pct} % moins cher que la veille.",
  versus_dearer: "En moyenne {pct} % plus cher que la veille.",
  answer: "L'électricité est la moins chère entre {from} et {to} UTC.",
  detail_local: "Soit de {from} à {to} en {zone}.",
  detail_average: "Moyenne de {avg} {label}, contre {mean} sur toute la journée.",
  detail_avoid: "Évitez {from} à {to} UTC, avec une moyenne de {avg}.",
  basis_kwh: "{words}, converti depuis EUR par MWh (1 MWh = 1000 kWh)",
  basis_fx: "{words}, converti depuis EUR par MWh au taux fixe 1 EUR = {rate} DKK",
  foot_note:
    "Les prix sont day-ahead, en {basis}. Les heures sont en UTC sauf fuseau horaire indiqué. À titre indicatif, pas un conseil financier.",
  foot_links: "Fonctionnement, décisions de conception et résultats des évaluations",
  privacy: "Confidentialité",
  fx_note: "1 EUR = {rate} DKK, le taux central fixe auquel la couronne est arrimée.",
  prices_unavailable: "Les prix ne sont pas disponibles pour le moment.",
  prices_unavailable_detail:
    "Le service de prix n'a pas répondu. Vous pouvez quand même poser une question ci-dessous, ou réessayer dans une minute.",
  ask_title: "Posez une question sur votre situation",
  ask_lead:
    "Dites-nous ce que vous devez faire fonctionner et pendant combien de temps. Vous recevez une courte note qui se termine par une décision.",
  your_question: "Votre question",
  question_placeholder:
    "J'ai besoin de 3 heures pour ma pompe à chaleur demain. Quand la lancer ?",
  get_brief: "Obtenir ma note",
  working: "En cours",
  count: "{n} sur {max}",
  or_try: "Ou essayez :",
  chip1: "pompe à chaleur, 3 heures",
  chip1_q: "J'ai besoin de 3 heures d'électricité demain pour ma pompe à chaleur. Quand la lancer ?",
  chip2: "les heures chères",
  chip2_q: "Quand l'électricité est-elle la plus chère demain, pour l'éviter ?",
  chip3: "prix négatifs",
  chip3_q: "Y aura-t-il des prix négatifs demain, et quand ?",
  why: "Pourquoi",
  caveats: "Réserves",
  meta:
    "D'après {source} pour {zone} ({basis}), une fenêtre de {hours} h, heures en UTC. Les chiffres de la note sont en {unit}{prices}. Référence {id}.",
  meta_source_synthetic: "des données de démonstration synthétiques",
  meta_source_real: "les prix day-ahead d'ENTSO-E",
  meta_basis_selector: "le pays que vous avez choisi",
  meta_basis_question: "le pays cité dans votre question",
  meta_basis_default: "le pays par défaut, aucun n'ayant été choisi ni cité",
  meta_prices: " ; le graphique est en {basis}",
  empty_question: "Saisissez d'abord une question.",
  network_error: "Impossible de joindre le service. Vérifiez votre connexion et réessayez.",
  err_killed: "Le service est en pause. Réessayez plus tard.",
  err_banned: "Trop de requêtes. Réessayez plus tard.",
  err_rate_limited: "Trop de requêtes. Réessayez plus tard.",
  err_budget: "Le budget du jour est épuisé. Réessayez demain (UTC).",
  err_busy: "Le service est occupé. Réessayez dans un instant.",
  err_bad_request: "La requête n'a pas pu être lue. Rechargez la page et réessayez.",
  err_too_large: "La requête est trop volumineuse.",
  err_bad_type: "La requête n'a pas pu être lue. Rechargez la page et réessayez.",
  err_bad_query: "Ce choix n'est pas disponible.",
  err_error: "Une erreur s'est produite. Réessayez plus tard.",
  err_model_error: "Je n'ai pas pu produire de note pour le moment. Réessayez plus tard.",
  err_empty: "Posez une question sur les prix day-ahead de l'électricité en Europe.",
  err_too_long: "Gardez la question sous 500 caractères.",
  err_delimiter: "Cette question contient du texte que je ne peux pas accepter.",
  err_off_topic:
    "Je ne réponds qu'aux questions sur les prix de l'électricité et le meilleur moment pour l'utiliser.",
  err_unsafe_output: "Je n'ai pas pu produire de réponse sûre. Reformulez la question.",
  err_no_data: "Les données de prix ne sont pas disponibles pour le moment.",
  err_no_prices: "Les données de prix ne sont pas disponibles pour le moment.",
  err_zone_unknown: "Je n'ai pas encore de données de prix pour ce pays.",
  err_zone_unsupported: "Ce pays n'est pas encore couvert. Choisissez-en un dans la liste.",
  err_denmark_ambiguous:
    "Le Danemark compte deux zones de prix : DK1 (Jutland et Fionie) et DK2 (Seeland et Copenhague). Choisissez-en une dans la liste des pays, ou citez une ville danoise dans votre question.",
};

// Country names: [short label for the list, name used in sentences].
const ZONE_NAMES = {
  DE_LU: {
    en: ["Germany/Luxembourg", "Germany and Luxembourg"],
    da: ["Tyskland/Luxembourg", "Tyskland og Luxembourg"],
    de: ["Deutschland/Luxemburg", "Deutschland und Luxemburg"],
    fr: ["Allemagne/Luxembourg", "l'Allemagne et le Luxembourg"],
  },
  FR: {
    en: ["France", "France"],
    da: ["Frankrig", "Frankrig"],
    de: ["Frankreich", "Frankreich"],
    fr: ["France", "la France"],
  },
  NL: {
    en: ["Netherlands", "the Netherlands"],
    da: ["Holland", "Holland"],
    de: ["Niederlande", "die Niederlande"],
    fr: ["Pays-Bas", "les Pays-Bas"],
  },
  BE: {
    en: ["Belgium", "Belgium"],
    da: ["Belgien", "Belgien"],
    de: ["Belgien", "Belgien"],
    fr: ["Belgique", "la Belgique"],
  },
  AT: {
    en: ["Austria", "Austria"],
    da: ["Østrig", "Østrig"],
    de: ["Österreich", "Österreich"],
    fr: ["Autriche", "l'Autriche"],
  },
  ES: {
    en: ["Spain", "Spain"],
    da: ["Spanien", "Spanien"],
    de: ["Spanien", "Spanien"],
    fr: ["Espagne", "l'Espagne"],
  },
  DK1: {
    en: ["Denmark West (DK1)", "Denmark West (DK1: Jutland and Funen)"],
    da: ["Vestdanmark (DK1)", "Vestdanmark (DK1: Jylland og Fyn)"],
    de: ["Westdänemark (DK1)", "Westdänemark (DK1: Jütland und Fünen)"],
    fr: ["Danemark Ouest (DK1)", "le Danemark Ouest (DK1 : Jutland et Fionie)"],
  },
  DK2: {
    en: ["Denmark East (DK2)", "Denmark East (DK2: Zealand and Copenhagen)"],
    da: ["Østdanmark (DK2)", "Østdanmark (DK2: Sjælland og København)"],
    de: ["Ostdänemark (DK2)", "Ostdänemark (DK2: Seeland und Kopenhagen)"],
    fr: ["Danemark Est (DK2)", "le Danemark Est (DK2 : Seeland et Copenhague)"],
  },
};

const I18N = (() => {
  let lang = "en";
  const has = (code) => Object.prototype.hasOwnProperty.call(STRINGS, code);

  const t = (key, vars) => {
    const text = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
    return vars ? text.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? vars[name] : "")) : text;
  };
  const hours = (n) => t(n === 1 ? "hour_one" : "hour_other", { n });
  const zone = (code, which) => {
    const entry = ZONE_NAMES[code];
    return entry ? entry[lang][which] : "";
  };
  // The page remembers the choice in this browser only. Without storage it still works.
  const remembered = () => {
    try {
      return localStorage.getItem("wb-lang");
    } catch (_) {
      return null;
    }
  };
  const remember = (code) => {
    try {
      localStorage.setItem("wb-lang", code);
    } catch (_) {
      // private window or blocked storage: the choice just lasts for this visit
    }
  };
  const initial = () => {
    const saved = remembered();
    if (saved && has(saved)) return saved;
    for (const tag of navigator.languages || [navigator.language]) {
      const code = String(tag).slice(0, 2).toLowerCase();
      if (has(code)) return code;
    }
    return "en";
  };

  return {
    t,
    hours,
    zone,
    get lang() {
      return lang;
    },
    get locale() {
      return LOCALES[lang];
    },
    set(code, persist) {
      if (!has(code)) return;
      lang = code;
      if (persist) remember(code);
    },
    initial,
  };
})();

if (typeof module !== "undefined") module.exports = { STRINGS, ZONE_NAMES, LOCALES, LANGUAGE_NAMES };
