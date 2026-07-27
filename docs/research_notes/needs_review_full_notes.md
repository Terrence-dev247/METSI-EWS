# Needs-Review Rows — Full Source Text

Pulled from the raw WP media-release scrape, since the `notes` column in
`tshwane_water_incidents_combined.csv` truncates right at the point where the
`[scope=...; geocode_flag=...]` annotation was appended.

---

## 1. INC-2023-101 — Booster-station vandalism
**Date:** 2023-02-24 | **Source:** https://www.tshwane.gov.za/?p=51356
**geocode_flag:** Check notes column for the specific pipeline/area named

> VANDALISM AFFECTING PIPELINES TO RAND WATER'S BOOSTER STATIONS
> Tshwane residents are informed about an emergency shutdown of the Rand Water supply in order to carry out repairs to its pipeline components that were vandalised yesterday evening. According to the water utility, the isolating valves for the meter that supplies the City of Ekurhuleni's Edenpark were damaged and, as a result, 52% of pumping to Palmiet Booster Pumping Station and 27% of pumping to Mapleton Booster Pumping Station will be affected.
>
> The utility anticipates taking ten hours to complete the repairs. Therefore, the levels of the following reservoirs will be depleted: Brakfontein, Bronberg, Hartebeeshoek, Klipfontein 1 and 2, Klipriviersbrug 1 and 2.
>
> [Long reservoir-by-suburb breakdown follows — affected reservoirs include Akasia, Bakenkop, Blair Athol, Erasmia, Klapperkop, Kosmosdal, Laudium, Lotus Gardens, Louwlardia, Mabopane, Rooihuiskraal, Saulsville, Soshanguve DD, Soshanguve L, Sunderland Ridge, Wonderboom — full suburb lists in the source if needed.]
>
> Roaming water tankers will be arranged to service all the affected areas. The City of Tshwane apologises for this unforeseen possible interruption and would like to urge ALL consumers to continue using water sparingly.
> Issued by Communication, Marketing and Events.

**Geocoding note:** The actual vandalism/repair site is the **Edenpark meter / isolating valves** feeding Palmiet and Mapleton Booster Pumping Stations — that's the point location, not the long list of downstream affected suburbs (those are just low-pressure ripple effects).

---

## 2. INC-2023-103 — B8 pipeline leak
**Date:** 2023-04-12 | **Source:** https://www.tshwane.gov.za/?p=53331
**geocode_flag:** Check notes column for which suburb the B8 pipeline serves

> EMERGENCY REPAIRS TO RAND WATER B8 PIPELINE WATER LEAK
> The City of Tshwane has been notified by Rand Water about emergency repair work on a major water leak on their B8 pipeline from Zuikerbosch Water Treatment Plant to Mapleton Booster Pumping Station tomorrow, 12 April 2023.
>
> According to the water utility, the leak is increasingly serious and will result in an increase of non-revenue water as well as possible flooding of the electromagnetic equipment which are currently submerged under water. The repair will take eight hours from 04:00 to 12:00 to conclude and during this period the Mapleton System will be reduced by 82%.
>
> This emergency shutdown will result in the depletion of the following Rand Water reservoirs that supply Tshwane: Vlakfontein 1 and 2, Bronberge.
>
> [Long list of affected reservoirs/suburbs follows: Garsfontein, Eersterust, Kilner Park, Koedoesnek LL, Magalieskruin, Mamelodi R1/R2, Montana, Moreleta, Murrayfield, Parkmore LL, Queenswood, Sinoville HL/LL, Villieria Peak Tanks, Waverley HL/LL, Gastonbury/Six Fountains/Silver Willows, Mooikloof, plus several named meters.]
>
> The City of Tshwane sincerely apologises for the inconvenience that may be encountered as a result of the above-mentioned repairs. The affected reservoirs will be filled to capacity prior to the shutdown and residents are urged to use water sparingly.
> Roaming water tankers will be arranged for all affected areas.

**Geocoding note:** The leak point is on the **B8 bulk pipeline between Zuikerbosch WTP and Mapleton Booster Pumping Station** — that's the asset location to geocode. Everything else is downstream reservoir/suburb fallout.

---

## 3. INC-2023-109 — Region 3 (multi-ward)
**Date:** 2023-07-20 | **Source:** https://www.tshwane.gov.za/?p=59290
**geocode_flag:** Region 3 spans multiple wards, no single point applies

> The City of Tshwane is aware of a water supply interruption that has affected parts of Region 3.
> A team of technicians had to shut down the water supply yesterday evening at **Waterkloof Reservoir** to effect the necessary repair work on a damaged water pipe along **Jan Shoba Street**.
>
> The following areas are affected: Bailey's Muckleneuk, Brooklyn, Groenkloof, Lynnwood, Menlo Park, Nieuw Muckleneuk, Waterkloof.
>
> The team has managed to conclude repairs this morning and the water supply has been opened. However, given that the system was empty, the network still needs to fill up before the supply to consumers normalises.
> The City pleads for patience during this period and wishes to apologise for the inconvenience caused by this unforeseen interruption.

**Geocoding note:** Unlike the other two, this one *does* have a clean point location — **Waterkloof Reservoir, Jan Shoba Street** — that's the actual repair site. The affected suburb list (Brooklyn, Groenkloof, Lynnwood, Menlo Park, Waterkloof, Nieuw Muckleneuk) is consistent with Waterkloof Reservoir's service area, so this one might not need "multi-ward" treatment at all — it's a single-point repair with multi-suburb downstream impact, same pattern as the other two.
