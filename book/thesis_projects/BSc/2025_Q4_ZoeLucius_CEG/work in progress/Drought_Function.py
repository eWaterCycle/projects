import numpy as np
import pandas as pd

def analyse_annual_deficits_MW(daily_data, flow_col, year_col, Q_crit, demand_zambia, demand_zimbabwe, eta=0.9, rho=1000, g=9.81, head=110.5):
    deficityears = []

    for year, group in daily_data.groupby(year_col):
        group[flow_col] = pd.to_numeric(group[flow_col], errors='coerce')

        total_deficit = (Q_crit - group[flow_col]).clip(lower=0).sum()
        total_surplus = (group[flow_col] - Q_crit).clip(lower=0).sum()

        if total_deficit > total_surplus:
            avg_net_deficit = (total_deficit - total_surplus) / len(group)
            power_shortage_MW = (eta * rho * g * avg_net_deficit * head) / 1e6

            shared_shortage_MW = power_shortage_MW / 2

            shortage_pct_zambia = round(100 * shared_shortage_MW / demand_zambia, 2)
            shortage_pct_zimbabwe = round(100 * shared_shortage_MW / demand_zimbabwe, 2)
            average_shortage = (shortage_pct_zambia + shortage_pct_zimbabwe) / 2
            
            if average_shortage >= 55:
                deficityears.append({'hydro_year': year, 'avg_net_deficit_m^3/s': round(avg_net_deficit, 2), 'power_shortage_MW': round(power_shortage_MW, 2),
                'Zambia_shortage_%': shortage_pct_zambia, 'Zimbabwe_shortage_%': shortage_pct_zimbabwe, 'severity': 'critical'})
            if 25 <= average_shortage < 55:
               deficityears.append({'hydro_year': year, 'avg_net_deficit_m^3/s': round(avg_net_deficit, 2), 'power_shortage_MW': round(power_shortage_MW, 2),
                'Zambia_shortage_%': shortage_pct_zambia, 'Zimbabwe_shortage_%': shortage_pct_zimbabwe, 'severity': 'high'})
            if average_shortage < 25:
                deficityears.append({'hydro_year': year, 'avg_net_deficit_m^3/s': round(avg_net_deficit, 2), 'power_shortage_MW': round(power_shortage_MW, 2),
                'Zambia_shortage_%': shortage_pct_zambia, 'Zimbabwe_shortage_%': shortage_pct_zimbabwe, 'severity': 'mild'})

    return pd.DataFrame(deficityears)


    