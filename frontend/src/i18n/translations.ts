export type Language = 'en' | 'hi';

/** English is the source of truth and the fallback for every missing key. */
export const FALLBACK_LANGUAGE: Language = 'en';

export interface TranslationDictionary {
  appName: string;
  subTitle: string;
  tagline: string;
  nav: {
    home: string;
    workspace: string;
    state: string;
    district: string;
    pipelines: string;
    audit: string;
    decoder: string;
    demoTour: string;
    askMap: string;
    resetDemo: string;
  };
  hero: {
    badge: string;
    headline: string;
    description: string;
    ctaExplore: string;
    ctaLifecycle: string;
    livePrecinct: string;
    registeredUnits: string;
    cryptographicSeal: string;
  };
  workspace: {
    parentUlpin: string;
    proposed3dId: string;
    plotArea: string;
    height: string;
    fsi: string;
    status: string;
    approved: string;
    pendingReview: string;
    correctionNeeded: string;
    explodeSlider: string;
    sliceSlider: string;
    xrayMode: string;
    tabs: {
      evidence: string;
      qaRules: string;
      rights: string;
      history: string;
      map2d: string;
      pipelines: string;
    };
  };
  roles: {
    districtVerifier: string;
    stateAdmin: string;
    builder: string;
    citizen: string;
    public: string;
  };
  lifecycle: {
    title: string;
    subtitle: string;
    stages: {
      data: string;
      location: string;
      ulpin: string;
      reconstruction: string;
      validation: string;
      officer: string;
      approval: string;
      qr: string;
    };
  };
  howItWorks: {
    title: string;
    subtitle: string;
    steps: {
      step1Title: string;
      step1Desc: string;
      step2Title: string;
      step2Desc: string;
      step3Title: string;
      step3Desc: string;
      step4Title: string;
      step4Desc: string;
      step5Title: string;
      step5Desc: string;
      step6Title: string;
      step6Desc: string;
    };
  };
  ingest: {
    breadcrumb: string;
    title: string;
    intro: string;
    introRestricted: string;
    standingHeading: string;
    standingPointCloudLabel: string;
    standingPointCloudText: string;
    standingPointCloudModelled: string;
    standingPointCloudTail: string;
    standingGnssLabel: string;
    standingGnssText: string;
    standingGeojsonLabel: string;
    standingGeojsonText: string;
    standingDroneLabel: string;
    standingDroneText: string;
    restrictedTitle: string;
    restrictedBuilder: string;
    restrictedOther: string;
    signInReviewer: string;
    signedInAs: string;
    provenanceHeading: string;
    fieldIsReal: string;
    fieldIsDerived: string;
    fieldAuthenticSource: string;
    fieldConfidenceTier: string;
    fieldSource: string;
    fieldDataType: string;
    fieldDerivationMethod: string;
    unspecified: string;
    notApplicable: string;
    yes: string;
    no: string;
    toneDerivedLabel: string;
    toneDerivedCaveat: string;
    toneExifGpsLabel: string;
    toneExifGpsCaveat: string;
    toneExifNoGpsLabel: string;
    toneExifNoGpsCaveat: string;
    toneAuthoritativeLabel: string;
    toneAuthoritativeCaveat: string;
    toneBuilderAssertedLabel: string;
    toneBuilderAssertedCaveat: string;
    toneRealInputLabel: string;
    toneRealInputCaveat: string;
    toneUnknownLabel: string;
    toneUnknownCaveat: string;
    errorSignInTitle: string;
    errorRejectedTitle: string;
    signIn: string;
    pointCloud: {
      title: string;
      standing: string;
      fileLabel: string;
      datasetLabel: string;
      submissionLabel: string;
      groundZLabel: string;
      groundZNote: string;
      submitBusy: string;
      submit: string;
      errorNoFile: string;
      errorFailed: string;
      toast: string;
      pipelineFailedTitle: string;
      pipelineFailedBody: string;
      fieldAssetId: string;
      fieldDatasetId: string;
      fieldFile: string;
      fieldFormat: string;
      fieldSize: string;
      fieldSha256: string;
      fieldPipelineOutput: string;
      outputNone: string;
      outputCompleted: string;
      resultDisclosure: string;
    };
    gnss: {
      title: string;
      standing: string;
      colIndex: string;
      colLat: string;
      colLon: string;
      colElev: string;
      colName: string;
      removePoint: string;
      descriptionLabel: string;
      descriptionPlaceholder: string;
      submissionLabel: string;
      addPoint: string;
      loadSample: string;
      submitBusy: string;
      submit: string;
      warningTitle: string;
      fieldPoints: string;
      fieldGeometry: string;
      fieldArea: string;
      fieldPerimeter: string;
      fieldCentroid: string;
      fieldCrs: string;
      notComputed: string;
      computationMethod: string;
      errorTooFew: string;
      errorBothCoords: string;
      errorNotNumbers: string;
      errorOutOfRange: string;
      errorOutsideIndia: string;
      errorGeneric: string;
      errorFailed: string;
      toast: string;
    };
    geojson: {
      title: string;
      standingAuthoritative: string;
      standingAsserted: string;
      fileLabel: string;
      loadedPrefix: string;
      payloadLabel: string;
      authorityLead: string;
      authorityBody: string;
      authorityDenied: string;
      sourceRequired: string;
      sourceOptional: string;
      submissionLabel: string;
      boundsNote: string;
      submitBusy: string;
      submit: string;
      errorUnreadable: string;
      errorNoPayload: string;
      errorInvalidJson: string;
      errorNotObject: string;
      errorAuthorityNeedsSource: string;
      errorFailed: string;
      toastNoList: string;
      toastRejected: string;
      toastImported: string;
      fieldFeaturesSent: string;
      fieldImported: string;
      fieldRejected: string;
      fieldTotalArea: string;
      unknown: string;
      rejectedBanner: string;
      rejectedBody: string;
      rejectedVertex: string;
      unknownListBody: string;
      noneRejected: string;
    };
    drone: {
      title: string;
      standing: string;
      fileLabel: string;
      metadataNote: string;
      submitBusy: string;
      submit: string;
      errorNoFile: string;
      errorFailed: string;
      toastGps: string;
      toastNoGps: string;
      badgeGps: string;
      badgeNoGps: string;
      fieldLat: string;
      fieldLon: string;
      fieldAltitude: string;
      fieldCaptureTime: string;
      fieldCamera: string;
      fieldSensor: string;
      fieldKeysRead: string;
      notInFile: string;
      notReported: string;
    };
  };
}

export const translations: Record<Language, TranslationDictionary> = {
  en: {
    appName: "Bhu-Drishti 3D",
    subTitle: "National 3D ULPIN & Vertical Property Cadastre",
    tagline: "Extending India's 14-character land parcel identifiers into governed 3D vertical strata and subterranean infrastructure.",
    nav: {
      home: "Overview",
      workspace: "3D Workspace",
      state: "State Overview",
      district: "District Queue",
      pipelines: "Pipeline Studio",
      audit: "Audit Trail",
      decoder: "3D ID Decoder",
      demoTour: "Guided Demo Tour",
      askMap: "Ask the Map",
      resetDemo: "Reset Demo",
    },
    hero: {
      badge: "SIH26011 STUDENT PROTOTYPE • NOT A GOVERNMENT SYSTEM",
      headline: "India's Property Map, Reimagined in 3D.",
      description: "A student prototype that sketches 3D massing above a synthetic demo land parcel. It is not connected to any government registry, and it does not produce verified, legal or air-right records.",
      ctaExplore: "Launch 3D Workspace",
      ctaLifecycle: "Explore Lifecycle",
      livePrecinct: "Airoli Sector 8 (400m × 400m)",
      registeredUnits: "21 Vertical Units",
      cryptographicSeal: "Ed25519 Signed",
    },
    workspace: {
      parentUlpin: "Parent Cadastral ULPIN",
      proposed3dId: "Proposed Bhu-Drishti 3D ID",
      plotArea: "Plot Area",
      height: "Building Height",
      fsi: "Calculated FSI",
      status: "Cadastral Status",
      approved: "Officially Approved",
      pendingReview: "Pending Verification",
      correctionNeeded: "Correction Required",
      explodeSlider: "Vertical Strata Separation",
      sliceSlider: "Horizontal Elevation Slice",
      xrayMode: "Subterranean X-Ray",
      tabs: {
        evidence: "Evidence (6)",
        qaRules: "QA Rules (12)",
        rights: "Rights Layer",
        history: "Time Slider",
        map2d: "2D Cadastre",
        pipelines: "Multi-Runtime Engine",
      },
    },
    roles: {
      districtVerifier: "Reviewer (demo role, not a government officer)",
      stateAdmin: "State Commissioner (Admin)",
      builder: "Builder (Apex Infra)",
      citizen: "Citizen / Flat Owner",
      public: "Public User (QR Proof)",
    },
    lifecycle: {
      title: "One Property. One Digital Identity. Full Visual Lifecycle.",
      subtitle: "From multi-source spatial evidence to tamper-evident official cadastral record and citizen verification.",
      stages: {
        data: "Multi-Source Evidence",
        location: "Spatial Georeferencing",
        ulpin: "Parent ULPIN Linkage",
        reconstruction: "AI 3D Mesh & Slicing",
        validation: "Topology & Clash Rules",
        officer: "Authority Review Queue",
        approval: "Ed25519 Cryptographic Sign",
        qr: "Public QR Verification",
      },
    },
    howItWorks: {
      title: "How Bhu-Drishti 3D Works",
      subtitle: "Six steps turning synthetic geospatial data into a 3D property prototype. Nothing here is a governed or official record.",
      steps: {
        step1Title: "01 Ingest & Normalize",
        step1Desc: "Six synthetic spatial streams (GIS, drone, LiDAR, CAD, CORS, DEM) placed in UTM 43N / EPSG:7755. No real sensor data is loaded.",
        step2Title: "02 Link Identity",
        step2Desc: "A 14-character parent identifier generated by this prototype, following the ULPIN format. It is not issued by any state registry and recognises nothing.",
        step3Title: "03 3D Reconstruction",
        step3Desc: "Statistical ground filtering, Z-density peak histogram slicing, and polyhedral extrusion generate building envelopes.",
        step4Title: "04 Topology & Geometry Checks",
        step4Desc: "Geometry and arithmetic checks on inter-unit disjointness and area ratios, run with PostGIS. These compare supplied numbers; they issue no compliance verdict.",
        step5Title: "05 Review & Record",
        step5Desc: "A reviewer role inside this prototype inspects discrepancies and records a decision. It is not a government appointment and the decision is not an official approval.",
        step6Title: "06 In-Process Audit Chain",
        step6Desc: "Events are chained with SHA-256 inside this process. No record is approved, the chain is not anchored anywhere external, and no DPDP compliance is claimed.",
      },
    },
    ingest: {
      breadcrumb: "Data Ingest",
      title: "Data Ingest Desk",
      intro: "Bring real survey material into the cadastre. Every result carries its provenance, and nothing ingested here is treated as authoritative unless the source says so.",
      introRestricted: "Accepts point clouds, GNSS survey points, parcel GeoJSON and drone metadata, and records where each came from.",
      standingHeading: "What these four routes can and cannot produce",
      standingPointCloudLabel: "Point cloud",
      standingPointCloudText: " — the uploaded file is real; the building and floor geometry returned from it is",
      standingPointCloudModelled: "modelled",
      standingPointCloudTail: "No authentic Indian airborne LiDAR exists in this project, so extracted output is never labelled as survey-grade.",
      standingGnssLabel: "GNSS",
      standingGnssText: " — real survey input. Areas are computed geodesically or in a projected CRS, never by treating degrees as metres.",
      standingGeojsonLabel: "Parcel GeoJSON",
      standingGeojsonText: " — authoritative only when an authorised role marks it so and names the source. Otherwise it is builder-asserted.",
      standingDroneLabel: "Drone image",
      standingDroneText: " — embedded EXIF metadata only. The image is not orthomosaicked and never becomes a cadastral source.",
      restrictedTitle: "Not available to your role",
      restrictedBuilder: "Ingestion writes into the cadastre. It is restricted to administrator and reviewer accounts, so a builder submission cannot alter the very record it is being submitted against.",
      restrictedOther: "Ingestion writes into the cadastre and is restricted to administrator and reviewer accounts.",
      signInReviewer: "Sign in with a reviewer account",
      signedInAs: "Signed in as",
      provenanceHeading: "Provenance",
      fieldIsReal: "Is real",
      fieldIsDerived: "Is derived",
      fieldAuthenticSource: "Authentic source",
      fieldConfidenceTier: "Confidence tier",
      fieldSource: "Source",
      fieldDataType: "Data type",
      fieldDerivationMethod: "Derivation method",
      unspecified: "UNSPECIFIED",
      notApplicable: "Not applicable — not derived",
      yes: "YES",
      no: "NO",
      toneDerivedLabel: "Derived / modelled",
      toneDerivedCaveat: "Computed by an automated pipeline from the uploaded file. It is not a survey measurement, carries no authority, and must not be presented or reused as surveyed ground.",
      toneExifGpsLabel: "Embedded capture metadata",
      toneExifGpsCaveat: "EXIF as written by the capture device, including its own GPS tag. That is the camera's claim about where it was; nothing here was independently surveyed or georeferenced.",
      toneExifNoGpsLabel: "Embedded metadata — no GPS",
      toneExifNoGpsCaveat: "No GPS tag was embedded in this file, so its position is unknown. Nothing was inferred from the file name, and no coordinates are held for it.",
      toneAuthoritativeLabel: "Authoritative — asserted at ingest",
      toneAuthoritativeCaveat: "An authorised role marked this upload authoritative. The platform records that declaration; it did not obtain the geometry from a land registry and cannot confirm title from it.",
      toneBuilderAssertedLabel: "Builder-asserted — not authoritative",
      toneBuilderAssertedCaveat: "Geometry exactly as asserted by the submitting party. No registry extract was attached, so these boundaries are unconfirmed and are not evidence of ownership.",
      toneRealInputLabel: "Real field input",
      toneRealInputCaveat: "Supplied as survey measurement. The areas and distances below are computed from these points geodesically or in a projected CRS — degrees are never treated as metres.",
      toneUnknownLabel: "Provenance not established",
      toneUnknownCaveat: "No authenticated source was attached, so the standing of this data cannot be claimed in either direction. Treat it as unverified input.",
      errorSignInTitle: "Sign in to ingest",
      errorRejectedTitle: "Ingest rejected",
      signIn: "Sign in",
      pointCloud: {
        title: "Point Cloud — LAS / LAZ / COPC / CSV / TXT",
        standing: "Derived / modelled output",
        fileLabel: "Point cloud file (max 100 MB)",
        datasetLabel: "Dataset name",
        submissionLabel: "Submission id (optional)",
        groundZLabel: "Ground Z (m)",
        groundZNote: "Ground Z is the assumed datum for the run. It is an input to a model, not a measured elevation.",
        submitBusy: "Processing…",
        submit: "Ingest point cloud",
        errorNoFile: "Choose a LAS, LAZ, COPC, CSV or TXT file first.",
        errorFailed: "Point-cloud upload failed",
        toast: "{file} received — {format}, output is modelled, not surveyed",
        pipelineFailedTitle: "Pipeline did not complete",
        pipelineFailedBody: "The file was received and hashed, but no geometry was produced from it. Nothing was modelled and nothing should be read into this result.",
        fieldAssetId: "Asset id",
        fieldDatasetId: "Dataset id",
        fieldFile: "File",
        fieldFormat: "Format",
        fieldSize: "Size",
        fieldSha256: "SHA-256",
        fieldPipelineOutput: "Pipeline output",
        outputNone: "None — run failed",
        outputCompleted: "Extraction completed",
        resultDisclosure: "Pipeline result (modelled)",
      },
      gnss: {
        title: "GNSS Survey Points — WGS84",
        standing: "Real field input",
        colIndex: "#",
        colLat: "Latitude",
        colLon: "Longitude",
        colElev: "Elev (m)",
        colName: "Name",
        removePoint: "Remove point {n}",
        descriptionLabel: "Description (optional)",
        descriptionPlaceholder: "Traverse run, survey reference…",
        submissionLabel: "Submission id (optional)",
        addPoint: "Add point",
        loadSample: "Load sample traverse",
        submitBusy: "Computing…",
        submit: "Ingest survey points",
        warningTitle: "Warning from the service",
        fieldPoints: "Points",
        fieldGeometry: "Geometry",
        fieldArea: "Area",
        fieldPerimeter: "Perimeter",
        fieldCentroid: "Centroid (lat, lon)",
        fieldCrs: "CRS",
        notComputed: "Not computed",
        computationMethod: "Computation method",
        errorTooFew: "At least 3 points are needed to form an area.",
        errorBothCoords: "Row {n}: both latitude and longitude are required.",
        errorNotNumbers: "Row {n}: latitude and longitude must be numbers.",
        errorOutOfRange: "Row {n}: out of range. Latitude must be −90…90, longitude −180…180.",
        errorOutsideIndia: "Row {n}: ({lat}, {lon}) is outside India bounds ({minLat}–{maxLat} lat, {minLon}–{maxLon} lon). The service rejects the whole request.",
        errorGeneric: "Check the point list.",
        errorFailed: "GNSS ingest failed",
        toast: "{n} survey points ingested",
      },
      geojson: {
        title: "Parcel GeoJSON — FeatureCollection",
        standingAuthoritative: "Authoritative (asserted)",
        standingAsserted: "Builder-asserted",
        fileLabel: "Load a .geojson / .json file (optional)",
        loadedPrefix: "Loaded:",
        payloadLabel: "GeoJSON payload (lon, lat order — FeatureCollection, Feature, Polygon or MultiPolygon)",
        authorityLead: "Mark this upload authoritative.",
        authorityBody: "Do this only if the geometry came from a registered title source — a registry extract, a gazette notification or a signed survey by a competent authority — and you can name that source below. This asserts the source's standing; the platform does not verify title and will record the assertion as yours.",
        authorityDenied: "Your role cannot mark an upload authoritative. Anything submitted from here is recorded as builder-asserted.",
        sourceRequired: "Source (required when authoritative)",
        sourceOptional: "Source (optional)",
        submissionLabel: "Submission id (optional)",
        boundsNote: "Coordinates are validated against India bounds. A single out-of-bounds vertex fails the whole request rather than importing part of the file.",
        submitBusy: "Validating…",
        submit: "Import parcels",
        errorUnreadable: "That file could not be read as text.",
        errorNoPayload: "Paste or upload a GeoJSON FeatureCollection first.",
        errorInvalidJson: "That is not valid JSON. Nothing was sent.",
        errorNotObject: "GeoJSON must be a JSON object.",
        errorAuthorityNeedsSource: "Marking this upload authoritative requires a source: name the registry, survey or gazette it came from.",
        errorFailed: "GeoJSON import failed",
        toastNoList: "{valid}/{total} features imported — rejection list not returned",
        toastRejected: "{valid}/{total} features imported — {rejected} rejected",
        toastImported: "{valid}/{total} features imported as {source}",
        fieldFeaturesSent: "Features sent",
        fieldImported: "Imported",
        fieldRejected: "Rejected",
        fieldTotalArea: "Total area",
        unknown: "Unknown",
        rejectedBanner: "{rejected} of {total} features were NOT imported",
        rejectedBody: "These features failed validation and were dropped. They are listed here so the shortfall is visible — fix the geometry and re-submit rather than assuming all {total} features are on record.",
        rejectedVertex: "vertex {coords}",
        unknownListBody: "The service did not return a rejection list, so how many of the {total} features were dropped is unknown. Confirm the count against the source file before treating this import as complete.",
        noneRejected: "No features were rejected — all {valid} passed validation.",
      },
      drone: {
        title: "Drone Image — Embedded EXIF metadata",
        standing: "Embedded metadata only",
        fileLabel: "Image file (max 50 MB)",
        metadataNote: "Only the metadata the capture device embedded is read. The imagery itself is not orthomosaicked, rectified or used as a cadastral source, and a GPS tag is the camera's own claim about its position — not an independently surveyed fix.",
        submitBusy: "Reading…",
        submit: "Read EXIF",
        errorNoFile: "Choose a JPG, TIFF or PNG image first.",
        errorFailed: "EXIF ingest failed",
        toastGps: "EXIF read from {file} — GPS tag present",
        toastNoGps: "EXIF read from {file} — no GPS tag",
        badgeGps: "GPS tag present",
        badgeNoGps: "No GPS tag",
        fieldLat: "Latitude",
        fieldLon: "Longitude",
        fieldAltitude: "Altitude",
        fieldCaptureTime: "Capture time",
        fieldCamera: "Camera",
        fieldSensor: "Sensor",
        fieldKeysRead: "EXIF keys read",
        notInFile: "Not in file",
        notReported: "Not reported",
      },
    },
  },
  hi: {
    appName: "Bhu-Drishti 3D",
    subTitle: "राष्ट्रीय 3D ULPIN एवं ऊर्ध्वाधर संपत्ति भूकर",
    tagline: "भारत के 14-वर्ण वाले भूमि पार्सल पहचानकर्ताओं को विनियमित 3D ऊर्ध्वाधर स्तरों और भूमिगत अवसंरचना तक विस्तारित करना।",
    nav: {
      home: "अवलोकन",
      workspace: "3D कार्यक्षेत्र",
      state: "राज्य अवलोकन",
      district: "जिला कतार",
      pipelines: "पाइपलाइन स्टूडियो",
      audit: "ऑडिट ट्रेल",
      decoder: "3D पहचानकर्ता डिकोडर",
      demoTour: "निर्देशित डेमो भ्रमण",
      askMap: "मानचित्र से पूछें",
      resetDemo: "डेमो रीसेट करें",
    },
    hero: {
      badge: "SIH26011 छात्र प्रोटोटाइप • सरकारी प्रणाली नहीं",
      headline: "भारत का संपत्ति मानचित्र, 3D में पुनर्कल्पित।",
      description: "एक छात्र प्रोटोटाइप, जो एक संश्लेषित डेमो भूमि पार्सल के ऊपर 3D मॉसिंग का रेखाचित्र बनाता है। यह किसी भी सरकारी रजिस्ट्री से जुड़ा नहीं है, और यह सत्यापित, कानूनी अथवा वायु-अधिकार संबंधी रिकॉर्ड नहीं बनाता।",
      ctaExplore: "3D कार्यक्षेत्र खोलें",
      ctaLifecycle: "जीवनचक्र देखें",
      livePrecinct: "ऐरोली सेक्टर 8 (400 मी × 400 मी)",
      registeredUnits: "21 ऊर्ध्वाधर इकाइयाँ",
      cryptographicSeal: "Ed25519 से हस्ताक्षरित",
    },
    workspace: {
      parentUlpin: "मूल भूकर ULPIN",
      proposed3dId: "प्रस्तावित Bhu-Drishti 3D पहचानकर्ता",
      plotArea: "भूखंड क्षेत्रफल",
      height: "भवन ऊँचाई",
      fsi: "परिकलित FSI",
      status: "भूकर स्थिति",
      approved: "आधिकारिक रूप से स्वीकृत",
      pendingReview: "सत्यापन लंबित",
      correctionNeeded: "सुधार आवश्यक",
      explodeSlider: "ऊर्ध्वाधर स्तर पृथक्करण",
      sliceSlider: "क्षैतिज उन्नत स्लाइस",
      xrayMode: "भूमिगत एक्स-रे",
      tabs: {
        evidence: "साक्ष्य (6)",
        qaRules: "QA नियम (12)",
        rights: "अधिकार परत",
        history: "समय स्लाइडर",
        map2d: "2D भूकर",
        pipelines: "बहु-रनटाइम इंजन",
      },
    },
    roles: {
      districtVerifier: "समीक्षक (डेमो भूमिका, सरकारी अधिकारी नहीं)",
      stateAdmin: "राज्य आयुक्त (प्रशासक)",
      builder: "बिल्डर (Apex Infra)",
      citizen: "नागरिक / फ्लैट मालिक",
      public: "सार्वजनिक उपयोगकर्ता (QR प्रमाण)",
    },
    lifecycle: {
      title: "एक संपत्ति। एक डिजिटल पहचान। पूर्ण दृश्य जीवनचक्र।",
      subtitle: "बहु-स्रोत स्थानिक साक्ष्य से छेड़छाड़-प्रतिरोधी आधिकारिक भूकर रिकॉर्ड और नागरिक सत्यापन तक।",
      stages: {
        data: "बहु-स्रोत साक्ष्य",
        location: "स्थानिक भू-संदर्भण",
        ulpin: "मूल ULPIN संबंधन",
        reconstruction: "AI 3D मेश एवं स्लाइसिंग",
        validation: "टोपोलॉजी एवं टकराव नियम",
        officer: "प्राधिकरण समीक्षा कतार",
        approval: "Ed25519 क्रिप्टोग्राफिक हस्ताक्षर",
        qr: "सार्वजनिक QR सत्यापन",
      },
    },
    howItWorks: {
      title: "Bhu-Drishti 3D कैसे कार्य करता है",
      subtitle: "छह चरणों में संश्लेषित भू-स्थानिक डेटा से 3D संपत्ति प्रोटोटाइप तक। यहाँ कुछ भी विनियमित या आधिकारिक रिकॉर्ड नहीं है।",
      steps: {
        step1Title: "01 अंग्रहण एवं सामान्यीकरण",
        step1Desc: "छह संश्लेषित स्थानिक धाराएँ (GIS, ड्रोन, LiDAR, CAD, CORS, DEM) UTM 43N / EPSG:7755 में रखी गई हैं। कोई वास्तविक सेंसर डेटा लोड नहीं किया जाता।",
        step2Title: "02 पहचान संबंधन",
        step2Desc: "ULPIN प्रारूप का अनुसरण करते हुए, इसी प्रोटोटाइप द्वारा तैयार किया गया 14-वर्ण वाला मूल पहचानकर्ता। यह किसी राज्य रजिस्ट्री द्वारा जारी नहीं किया गया है और यह किसी को भी पहचानता नहीं है।",
        step3Title: "03 3D पुनर्निर्माण",
        step3Desc: "सांख्यिकीय भू-पृथक्करण, Z-घनत्व चरम मान हिस्टोग्राम स्लाइसिंग तथा बहुभुजीय एक्सट्रूजन से भवन आवरण तैयार होते हैं।",
        step4Title: "04 टोपोलॉजी एवं ज्यामिति जाँचें",
        step4Desc: "PostGIS के साथ विभिन्न इकाइयों के बीच असंबद्धता तथा क्षेत्रफल अनुपात पर ज्यामितीय और अंकगणितीय जाँचें चलाई जाती हैं। ये केवल दिए गए आँकड़ों की तुलना करती हैं; ये कोई अनुपालन निर्णय नहीं देतीं।",
        step5Title: "05 समीक्षा एवं अभिलेखन",
        step5Desc: "इसी प्रोटोटाइप में एक समीक्षक भूमिका विसंगतियों की जाँच करती है और निर्णय दर्ज़ करती है। यह कोई सरकारी नियुक्ति नहीं है और यह निर्णय कोई आधिकारिक स्वीकृति नहीं है।",
        step6Title: "06 प्रक्रिया-आंतरिक ऑडिट शृंखला",
        step6Desc: "इसी प्रक्रिया के भीतर घटनाओं को SHA-256 से शृंखलाबद्ध किया जाता है। कोई रिकॉर्ड स्वीकृत नहीं होता, यह शृंखला किसी बाहरी स्रोत पर आलंकित नहीं है, और DPDP अनुपालन का कोई दावा नहीं किया जाता।",
      },
    },
    ingest: {
      breadcrumb: "डेटा इंगेस्ट",
      title: "डेटा इंगेस्ट डेस्क",
      intro: "वास्तविक सर्वेक्षण सामग्री कैडास्ट्र में लाएँ। प्रत्येक परिणाम अपनी प्रोवेनेंस के साथ आता है, और यहाँ अंग्रीकृत किया गया कुछ भी प्राधिकृत नहीं माना जाता जब तक कि उसका स्रोत ऐसा न कहे।",
      introRestricted: "पॉइंट क्लाउड, GNSS सर्वेक्षण बिंदु, पार्सल GeoJSON और ड्रोन मेटाडेटा स्वीकार करता है, और प्रत्येक का स्रोत दर्ज करता है।",
      standingHeading: "ये चार मार्ग क्या बना सकते हैं और क्या नहीं",
      standingPointCloudLabel: "पॉइंट क्लाउड",
      standingPointCloudText: " — अपलोड की गई फ़ाइल वास्तविक है; इससे लौटाई गई भवन और मंज़िल ज्यामिति",
      standingPointCloudModelled: "मॉडल की गई",
      standingPointCloudTail: "इस परियोजना में भारत का कोई प्रामाणिक वायु-माध्यमिक LiDAR मौजूद नहीं है, इसलिए निकाला गया आउटपुट कभी सर्वेक्षण-ग्रेड के रूप में चिह्नित नहीं होता।",
      standingGnssLabel: "GNSS",
      standingGnssText: " — वास्तविक सर्वेक्षण इनपुट। क्षेत्रफल ज्यामितीय रूप से या प्रक्षेपित CRS में गणना किया जाता है, डिग्री को मीटर कभी नहीं माना जाता।",
      standingGeojsonLabel: "पार्सल GeoJSON",
      standingGeojsonText: " — प्राधिकृत तभी जब कोई अधिकृत भूमिका इसे ऐसा चिह्नित करे और स्रोत का नाम बताए। अन्यथा यह बिल्डर-एसर्टेड है।",
      standingDroneLabel: "ड्रोन छवि",
      standingDroneText: " — केवल एम्बेडेड EXIF मेटाडेटा। छवि ऑर्थोमोज़ेक नहीं की जाती और कभी कैडास्ट्रल स्रोत नहीं बनती।",
      restrictedTitle: "आपकी भूमिका के लिए उपलब्ध नहीं",
      restrictedBuilder: "इंगेस्ट कैडास्ट्र में लिखता है। यह केवल प्रशासक और समीक्षक खातों तक सीमित है, ताकि बिल्डर सबमिशन उसी रिकॉर्ड को न बदल सके जिसके विरुद्ध दायर किया गया है।",
      restrictedOther: "इंगेस्ट कैडास्ट्र में लिखता है और केवल प्रशासक तथा समीक्षक खातों तक सीमित है।",
      signInReviewer: "समीक्षक खाते से साइन इन करें",
      signedInAs: "साइन इन:",
      provenanceHeading: "प्रोवेनेंस",
      fieldIsReal: "वास्तविक है",
      fieldIsDerived: "व्युत्पन्न है",
      fieldAuthenticSource: "प्रामाणिक स्रोत",
      fieldConfidenceTier: "विश्वास स्तर",
      fieldSource: "स्रोत",
      fieldDataType: "डेटा प्रकार",
      fieldDerivationMethod: "व्युत्पन्नि विधि",
      unspecified: "अनिर्दिष्ट",
      notApplicable: "लागू नहीं — व्युत्पन्न नहीं",
      yes: "हाँ",
      no: "नहीं",
      toneDerivedLabel: "व्युत्पन्न / मॉडल की गई",
      toneDerivedCaveat: "अपलोड की गई फ़ाइल से स्वचालित पाइपलाइन द्वारा गणना की गई। यह सर्वेक्षण माप नहीं है, इसमें कोई प्राधिकार नहीं है, और इसे सर्वेक्षित भूमि के रूप में प्रस्तुत या पुनः उपयोग नहीं किया जाना चाहिए।",
      toneExifGpsLabel: "एम्बेडेड कैप्चर मेटाडेटा",
      toneExifGpsCaveat: "कैप्चर डिवाइस द्वारा लिखा गया EXIF, जिसमें उसका अपना GPS टैग भी शामिल है। यह कैमरे का दावा है कि वह कहाँ था; यहाँ कुछ भी स्वतंत्र रूप से सर्वेक्षित या जियोरिफ़ेरेंस्ड नहीं है।",
      toneExifNoGpsLabel: "एम्बेडेड मेटाडेटा — GPS नहीं",
      toneExifNoGpsCaveat: "इस फ़ाइल में कोई GPS टैग एम्बेडेड नहीं है, इसलिए इसकी स्थिति अज्ञात है। फ़ाइल के नाम से कुछ भी अनुमानित नहीं किया गया, और इसके लिए कोई निर्देशांक नहीं रखे गए हैं।",
      toneAuthoritativeLabel: "प्राधिकृत — इंगेस्ट पर घोषित",
      toneAuthoritativeCaveat: "किसी अधिकृत भूमिका ने इस अपलोड को प्राधिकृत चिह्नित किया। प्लेटफ़ॉर्म वह घोषणा दर्ज करता है; इसने ज्यामिति किसी भू-रजिस्ट्री से प्राप्त नहीं की और उससे स्वामित्व की पुष्टि नहीं कर सकता।",
      toneBuilderAssertedLabel: "बिल्डर-एसर्टेड — प्राधिकृत नहीं",
      toneBuilderAssertedCaveat: "जमा करने वाले पक्ष द्वारा ठीक वैसी ही ज्यामिति जैसा उसने कहा। कोई रजिस्ट्री निष्कर्ष संलग्न नहीं है, इसलिए ये सीमाएँ अपुष्ट हैं और स्वामित्व का प्रमाण नहीं हैं।",
      toneRealInputLabel: "वास्तविक क्षेत्र इनपुट",
      toneRealInputCaveat: "सर्वेक्षण माप के रूप में दिया गया। नीचे दिया गया क्षेत्रफल और दूरियाँ इन बिंदुओं से ज्यामितीय रूप से या प्रक्षेपित CRS में गणित की जाती हैं — डिग्री को कभी मीटर नहीं माना जाता।",
      toneUnknownLabel: "प्रोवेनेंस स्थापित नहीं",
      toneUnknownCaveat: "कोई प्रामाणिक स्रोत संलग्न नहीं है, इसलिए इस डेटा की स्थिति का दावा किसी भी दिशा में नहीं किया जा सकता। इसे असत्यापित इनपुट मानें।",
      errorSignInTitle: "इंगेस्ट करने के लिए साइन इन करें",
      errorRejectedTitle: "इंगेस्ट अस्वीकृत",
      signIn: "साइन इन करें",
      pointCloud: {
        title: "पॉइंट क्लाउड — LAS / LAZ / COPC / CSV / TXT",
        standing: "व्युत्पन्न / मॉडल की गई आउटपुट",
        fileLabel: "पॉइंट क्लाउड फ़ाइल (अधिकतम 100 MB)",
        datasetLabel: "डेटासेट नाम",
        submissionLabel: "सबमिशन आईडी (वैकल्पिक)",
        groundZLabel: "ग्राउंड Z (मी)",
        groundZNote: "ग्राउंड Z इस रन के लिए अनुमानित डेटम है। यह मॉडल का इनपुट है, मापा गया उच्चाई नहीं।",
        submitBusy: "प्रोसेस हो रहा है…",
        submit: "पॉइंट क्लाउड इंगेस्ट करें",
        errorNoFile: "पहले एक LAS, LAZ, COPC, CSV या TXT फ़ाइल चुनें।",
        errorFailed: "पॉइंट क्लाउड अपलोड विफल",
        toast: "{file} प्राप्त — {format}, आउटपुट मॉडल की गई है, सर्वेक्षित नहीं",
        pipelineFailedTitle: "पाइपलाइन पूरी नहीं हुई",
        pipelineFailedBody: "फ़ाइल प्राप्त और हैश की गई, लेकिन उससे कोई ज्यामिति नहीं बनी। कुछ भी मॉडल नहीं किया गया और इस परिणाम से कुछ भी नहीं निकाला जाना चाहिए।",
        fieldAssetId: "एसेट आईडी",
        fieldDatasetId: "डेटासेट आईडी",
        fieldFile: "फ़ाइल",
        fieldFormat: "प्रारूप",
        fieldSize: "आकार",
        fieldSha256: "SHA-256",
        fieldPipelineOutput: "पाइपलाइन आउटपुट",
        outputNone: "कोई नहीं — रन विफल",
        outputCompleted: "निष्कर्षन पूर्ण",
        resultDisclosure: "पाइपलाइन परिणाम (मॉडल की गई)",
      },
      gnss: {
        title: "GNSS सर्वेक्षण बिंदु — WGS84",
        standing: "वास्तविक क्षेत्र इनपुट",
        colIndex: "#",
        colLat: "अक्षांश",
        colLon: "देशांतर",
        colElev: "ऊँचाई (मी)",
        colName: "नाम",
        removePoint: "बिंदु {n} हटाएँ",
        descriptionLabel: "विवरण (वैकल्पिक)",
        descriptionPlaceholder: "ट्रैवर्स रन, सर्वेक्षण संदर्भ…",
        submissionLabel: "सबमिशन आईडी (वैकल्पिक)",
        addPoint: "बिंदु जोड़ें",
        loadSample: "नमूना ट्रैवर्स लोड करें",
        submitBusy: "गणना हो रही है…",
        submit: "सर्वेक्षण बिंदु इंगेस्ट करें",
        warningTitle: "सेवा से चेतावनी",
        fieldPoints: "बिंदु",
        fieldGeometry: "ज्यामिति",
        fieldArea: "क्षेत्रफल",
        fieldPerimeter: "परिधि",
        fieldCentroid: "केन्द्रक (अक्षांश, देशांतर)",
        fieldCrs: "CRS",
        notComputed: "गणना नहीं हुई",
        computationMethod: "गणना विधि",
        errorTooFew: "क्षेत्र बनाने के लिए कम से कम 3 बिंदु चाहिए।",
        errorBothCoords: "पंक्ति {n}: अक्षांश और देशांतर दोनों आवश्यक हैं।",
        errorNotNumbers: "पंक्ति {n}: अक्षांश और देशांतर संख्याएँ होनी चाहिए।",
        errorOutOfRange: "पंक्ति {n}: सीमा से बाहर। अक्षांश −90…90, देशांतर −180…180 होना चाहिए।",
        errorOutsideIndia: "पंक्ति {n}: ({lat}, {lon}) भारत की सीमा ({minLat}–{maxLat} अक्षांश, {minLon}–{maxLon} देशांतर) से बाहर है। सेवा पूरा अनुरोध अस्वीकार कर देती है।",
        errorGeneric: "बिंदु सूची जाँचें।",
        errorFailed: "GNSS इंगेस्ट विफल",
        toast: "{n} सर्वेक्षण बिंदु इंगेस्ट किए गए",
      },
      geojson: {
        title: "पार्सल GeoJSON — FeatureCollection",
        standingAuthoritative: "प्राधिकृत (घोषित)",
        standingAsserted: "बिल्डर-एसर्टेड",
        fileLabel: "कोई .geojson / .json फ़ाइल लोड करें (वैकल्पिक)",
        loadedPrefix: "लोड हुई:",
        payloadLabel: "GeoJSON पेलोड (lon, lat क्रम — FeatureCollection, Feature, Polygon या MultiPolygon)",
        authorityLead: "इस अपलोड को प्राधिकृत चिह्नित करें।",
        authorityBody: "यह केवल तभी करें जब ज्यामिति किसी पंजीकृत टाइटल स्रोत से आई हो — रजिस्ट्री निष्कर्ष, राजपत्र अधिसूचना या सक्षम प्राधिकारी द्वारा हस्ताक्षरित सर्वेक्षण — और आप नीचे उस स्रोत का नाम बता सकें। यह स्रोत की स्थिति का दावा करता है; प्लेटफ़ॉर्म स्वामित्व की पुष्टि नहीं करता और इस दावे को आपका दर्ज करेगा।",
        authorityDenied: "आपकी भूमिका किसी अपलोड को प्राधिकृत चिह्नित नहीं कर सकती। यहाँ से जमा किया गया कुछ भी बिल्डर-एसर्टेड दर्ज होता है।",
        sourceRequired: "स्रोत (प्राधिकृत होने पर आवश्यक)",
        sourceOptional: "स्रोत (वैकल्पिक)",
        submissionLabel: "सबमिशन आईडी (वैकल्पिक)",
        boundsNote: "निर्देशांक भारत की सीमा के विरुद्ध जाँचे जाते हैं। एक भी सीमा से बाहर शीर्ष पूरे अनुरोध को विफल कर देता है, न कि फ़ाइल का एक हिस्सा आयात होता है।",
        submitBusy: "सत्यापन हो रहा है…",
        submit: "पार्सल आयात करें",
        errorUnreadable: "वह फ़ाइल पाठ के रूप में नहीं पढ़ी जा सकी।",
        errorNoPayload: "पहले कोई GeoJSON FeatureCollection पेस्ट करें या अपलोड करें।",
        errorInvalidJson: "यह मान्य JSON नहीं है। कुछ भी नहीं भेजा गया।",
        errorNotObject: "GeoJSON एक JSON ऑब्जेक्ट होना चाहिए।",
        errorAuthorityNeedsSource: "इस अपलोड को प्राधिकृत चिह्नित करने के लिए स्रोत आवश्यक है: वह रजिस्ट्री, सर्वेक्षण या राजपत्र बताएँ जहाँ से यह आया।",
        errorFailed: "GeoJSON आयात विफल",
        toastNoList: "{valid}/{total} फ़ीचर आयात — अस्वीकृति सूची नहीं मिली",
        toastRejected: "{valid}/{total} फ़ीचर आयात — {rejected} अस्वीकृत",
        toastImported: "{valid}/{total} फ़ीचर {source} के रूप में आयात",
        fieldFeaturesSent: "भेजी गई फ़ीचर",
        fieldImported: "आयात",
        fieldRejected: "अस्वीकृत",
        fieldTotalArea: "कुल क्षेत्रफल",
        unknown: "अज्ञात",
        rejectedBanner: "{total} में से {rejected} फ़ीचर आयात नहीं हुईं",
        rejectedBody: "ये फ़ीचर सत्यापन में विफल होकर छोड़ दी गईं। इन्हें यहाँ सूचीबद्ध किया गया है ताकि कमी दिखाई दे — यह मान लेने के बजाय ज्यामिति ठीक करके पुनः जमा करें कि सभी {total} फ़ीचर दर्ज हैं।",
        rejectedVertex: "शीर्ष {coords}",
        unknownListBody: "सेवा ने अस्वीकृति सूची नहीं लौटाई, इसलिए {total} में से कितनी फ़ीचर छोड़ी गईं यह अज्ञात है। इस आयात को पूरा मानने से पहले संख्या को स्रोत फ़ाइल से सत्यापित करें।",
        noneRejected: "कोई सुविधा अस्वीकृत नहीं — सभी {valid} सत्यापन से गुज़रीं।",
      },
      drone: {
        title: "ड्रोन छवि — एम्बेडेड EXIF मेटाडेटा",
        standing: "केवल एम्बेडेड मेटाडेटा",
        fileLabel: "छवि फ़ाइल (अधिकतम 50 MB)",
        metadataNote: "केवल वही मेटाडेटा पढ़ा जाता है जो कैप्चर डिवाइस ने एम्बेड किया है। छवि स्वयं ऑर्थोमोज़ेक, रेक्टिफाई नहीं की जाती और कैडास्ट्रल स्रोत के रूप में उपयोग नहीं होती, तथा GPS टैग कैमरे का अपना दावा है कि वह कहाँ था — स्वतंत्र सर्वेक्षित निर्धारण नहीं।",
        submitBusy: "पढ़ा जा रहा है…",
        submit: "EXIF पढ़ें",
        errorNoFile: "पहले एक JPG, TIFF या PNG छवि चुनें।",
        errorFailed: "EXIF इंगेस्ट विफल",
        toastGps: "{file} से EXIF पढ़ा गया — GPS टैग मौजूद",
        toastNoGps: "{file} से EXIF पढ़ा गया — कोई GPS टैग नहीं",
        badgeGps: "GPS टैग मौजूद",
        badgeNoGps: "कोई GPS टैग नहीं",
        fieldLat: "अक्षांश",
        fieldLon: "देशांतर",
        fieldAltitude: "ऊँचाई",
        fieldCaptureTime: "कैप्चर समय",
        fieldCamera: "कैमरा",
        fieldSensor: "सेंसर",
        fieldKeysRead: "पढ़े गए EXIF की",
        notInFile: "फ़ाइल में नहीं",
        notReported: "रिपोर्ट नहीं किया गया",
      },
    },
  },
};
