"""Common vehicles by outside size, for garage_fit and driveway_fit.

Each row: label, kind, length, body width (mirrors folded), width with mirrors out, height, door clearance, ramp.
Metres. Length, widths and height are the makers' published figures for a recent model year (2023 to 2025, base
trim, rounded to 1 cm), typed in from their spec sheets; trims, racks, lifts and tyres change them, so every
figure is an editable assumption in the result. Door clearance is the room beside the body a front door needs to
open far enough to get out without squeezing (longer doors on coupes and crew cabs need more). Ramp is the clear
width beside a side-entry wheelchair van for its ramp and the chair to turn onto it (about 8 ft, the figure
BraunAbility and VMI give buyers).
"""
from __future__ import annotations

from typing import NamedTuple


class Vehicle(NamedTuple):
    label: str
    kind: str          # car, suv, pickup, van, motorcycle, trailer, rv, cart
    length: float
    width: float       # body, mirrors folded
    mirrors: float     # mirrors out
    height: float
    door: float        # clearance beside the body to open a front door and get out
    ramp: float = 0.0  # clear width beside the vehicle for a side ramp (wheelchair vans)
    towed: bool = False  # trailers and boats: no doors to open, pushed or backed in


VEHICLES: dict[str, Vehicle] = {
    # pickups
    "ford_f150": Vehicle("Ford F-150 SuperCrew, 5.5 ft bed", "pickup", 5.89, 2.03, 2.44, 1.96, 0.90),
    "ford_f150_long": Vehicle("Ford F-150 SuperCrew, 6.5 ft bed", "pickup", 6.19, 2.03, 2.44, 1.96, 0.90),
    "ford_f150_lightning": Vehicle("Ford F-150 Lightning", "pickup", 5.91, 2.03, 2.44, 1.99, 0.90),
    "ford_f250": Vehicle("Ford F-250 Super Duty Crew Cab", "pickup", 6.76, 2.03, 2.67, 2.06, 0.95),
    "chevy_silverado": Vehicle("Chevrolet Silverado 1500 Crew Cab", "pickup", 5.89, 2.06, 2.41, 1.93, 0.90),
    "gmc_sierra": Vehicle("GMC Sierra 1500 Crew Cab", "pickup", 5.89, 2.06, 2.41, 1.95, 0.90),
    "ram_1500": Vehicle("Ram 1500 Crew Cab, 5.7 ft bed", "pickup", 5.92, 2.08, 2.47, 1.97, 0.90),
    "toyota_tundra": Vehicle("Toyota Tundra CrewMax", "pickup", 5.93, 2.04, 2.43, 1.98, 0.90),
    "toyota_tacoma": Vehicle("Toyota Tacoma Double Cab", "pickup", 5.41, 1.96, 2.20, 1.86, 0.85),
    "ford_ranger": Vehicle("Ford Ranger SuperCrew", "pickup", 5.35, 1.92, 2.20, 1.87, 0.85),
    "ford_maverick": Vehicle("Ford Maverick", "pickup", 5.07, 1.84, 2.07, 1.75, 0.80),
    "honda_ridgeline": Vehicle("Honda Ridgeline", "pickup", 5.33, 2.00, 2.20, 1.80, 0.85),
    "rivian_r1t": Vehicle("Rivian R1T", "pickup", 5.51, 2.02, 2.21, 1.99, 0.85),
    "tesla_cybertruck": Vehicle("Tesla Cybertruck", "pickup", 5.68, 2.03, 2.41, 1.79, 0.90),
    # SUVs
    "chevy_suburban": Vehicle("Chevrolet Suburban", "suv", 5.73, 2.06, 2.30, 1.92, 0.90),
    "chevy_tahoe": Vehicle("Chevrolet Tahoe", "suv", 5.35, 2.06, 2.30, 1.93, 0.90),
    "cadillac_escalade": Vehicle("Cadillac Escalade", "suv", 5.38, 2.06, 2.31, 1.95, 0.90),
    "ford_expedition": Vehicle("Ford Expedition", "suv", 5.33, 2.03, 2.29, 1.95, 0.90),
    "ford_explorer": Vehicle("Ford Explorer", "suv", 5.05, 2.00, 2.29, 1.78, 0.85),
    "jeep_grand_cherokee": Vehicle("Jeep Grand Cherokee", "suv", 4.91, 1.98, 2.15, 1.79, 0.85),
    "jeep_wrangler": Vehicle("Jeep Wrangler Unlimited", "suv", 4.88, 1.89, 2.10, 1.87, 0.80),
    "toyota_4runner": Vehicle("Toyota 4Runner", "suv", 4.83, 1.93, 2.10, 1.82, 0.85),
    "toyota_highlander": Vehicle("Toyota Highlander", "suv", 4.95, 1.93, 2.16, 1.73, 0.85),
    "toyota_rav4": Vehicle("Toyota RAV4", "suv", 4.60, 1.86, 2.09, 1.70, 0.80),
    "honda_crv": Vehicle("Honda CR-V", "suv", 4.70, 1.87, 2.10, 1.68, 0.80),
    "kia_telluride": Vehicle("Kia Telluride", "suv", 5.00, 1.99, 2.20, 1.75, 0.85),
    "tesla_model_y": Vehicle("Tesla Model Y", "suv", 4.75, 1.92, 2.13, 1.62, 0.80),
    "rivian_r1s": Vehicle("Rivian R1S", "suv", 5.10, 2.02, 2.21, 1.97, 0.85),
    "land_rover_defender": Vehicle("Land Rover Defender 110", "suv", 5.02, 2.01, 2.11, 1.97, 0.85),
    "subaru_outback": Vehicle("Subaru Outback", "suv", 4.87, 1.87, 2.06, 1.67, 0.80),
    # cars
    "tesla_model_3": Vehicle("Tesla Model 3", "car", 4.72, 1.85, 2.09, 1.44, 0.80),
    "toyota_camry": Vehicle("Toyota Camry", "car", 4.92, 1.84, 2.05, 1.44, 0.80),
    "toyota_corolla": Vehicle("Toyota Corolla", "car", 4.63, 1.78, 1.99, 1.44, 0.75),
    "honda_civic": Vehicle("Honda Civic sedan", "car", 4.67, 1.80, 2.00, 1.41, 0.75),
    "honda_accord": Vehicle("Honda Accord", "car", 4.97, 1.86, 2.07, 1.45, 0.80),
    "bmw_3": Vehicle("BMW 3 Series", "car", 4.71, 1.83, 2.07, 1.44, 0.80),
    "mini_cooper": Vehicle("Mini Cooper hardtop", "car", 3.88, 1.73, 1.93, 1.41, 0.85),
    "ford_mustang": Vehicle("Ford Mustang coupe", "car", 4.81, 1.92, 2.10, 1.40, 1.05),
    "chevy_corvette": Vehicle("Chevrolet Corvette", "car", 4.63, 1.93, 2.06, 1.23, 1.05),
    "porsche_911": Vehicle("Porsche 911", "car", 4.52, 1.85, 2.02, 1.30, 1.00),
    "mazda_mx5": Vehicle("Mazda MX-5 Miata", "car", 3.92, 1.73, 1.90, 1.23, 0.90),
    # vans
    "honda_odyssey": Vehicle("Honda Odyssey", "van", 5.21, 1.99, 2.24, 1.77, 0.80),
    "toyota_sienna": Vehicle("Toyota Sienna", "van", 5.18, 1.99, 2.21, 1.78, 0.80),
    "chrysler_pacifica": Vehicle("Chrysler Pacifica", "van", 5.18, 2.02, 2.27, 1.78, 0.80),
    "wheelchair_van": Vehicle("Side-entry wheelchair van (Sienna or Pacifica conversion)", "van", 5.18, 2.02, 2.27,
                              1.78, 0.80, ramp=2.44),
    "ford_transit_low": Vehicle("Ford Transit 130 in low roof", "van", 5.59, 2.06, 2.47, 2.12, 0.85),
    "sprinter_high": Vehicle("Mercedes Sprinter 144 in high roof", "van", 5.93, 2.02, 2.43, 2.72, 0.85),
    # two wheels, carts
    "motorcycle_touring": Vehicle("Touring motorcycle (Harley Road Glide)", "motorcycle", 2.60, 0.98, 0.98, 1.38, 0.60),
    "motorcycle_sport": Vehicle("Sport motorcycle", "motorcycle", 2.08, 0.75, 0.75, 1.13, 0.60),
    "golf_cart": Vehicle("Golf cart", "cart", 2.40, 1.20, 1.20, 1.80, 0.50),
    # towed and RVs (garage door height and driveway length matter most)
    "utility_trailer": Vehicle("Utility trailer, 5 x 10 ft, with tongue", "trailer", 4.30, 2.00, 2.00, 1.00, 0.45, towed=True),
    "teardrop_trailer": Vehicle("Teardrop camper trailer", "trailer", 4.60, 1.90, 1.90, 1.60, 0.45, towed=True),
    "boat_20ft": Vehicle("20 ft bowrider on its trailer", "trailer", 7.00, 2.59, 2.59, 2.40, 0.45, towed=True),
    "jet_ski": Vehicle("Jet ski on its trailer", "trailer", 4.30, 1.60, 1.60, 1.40, 0.45, towed=True),
    "travel_trailer_25ft": Vehicle("25 ft travel trailer", "trailer", 7.60, 2.44, 2.44, 3.20, 0.45, towed=True),
    "class_b_rv": Vehicle("Class B camper van (Sprinter 144 in 4x4)", "rv", 5.94, 2.03, 2.43, 2.82, 0.85),
    "class_c_rv": Vehicle("Class C motorhome, 24 ft", "rv", 7.40, 2.39, 2.70, 3.35, 0.85),
    "class_a_rv": Vehicle("Class A motorhome, 35 ft", "rv", 10.70, 2.59, 2.90, 3.96, 0.85),
}

# other things people keep in a garage, as floor footprints (length, depth, height) in metres
THINGS = {
    "workbench": ((1.83, 0.61, 0.91), "6 ft workbench, 24 in deep, plus 0.75 m to stand at it"),
    "ev_charger": ((0.35, 0.20, 0.45), "Wall charger (Level 2), 1.2 m up, within reach of a 7.5 m cable"),
    "motorcycle": ((2.30, 0.90, 1.20), "A motorcycle on its stand"),
    "bikes": ((1.80, 0.60, 1.10), "Three bicycles side by side on a floor rack"),
    "squat_rack": ((1.30, 1.30, 2.30), "Power rack, 4 ft square and 7.5 ft tall, on a 2.4 m platform"),
}
STAND_M = 0.75   # standing room in front of a bench
GYM_PLATFORM_M = 2.44  # an 8 x 8 ft lifting platform the rack stands on
