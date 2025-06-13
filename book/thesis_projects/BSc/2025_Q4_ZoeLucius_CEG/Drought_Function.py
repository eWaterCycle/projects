## Just the drought analyser function
import numpy as np
import pandas as pd

def analyse_annual_deficits_MW(daily_data, flow_col, crit_data, year_col, crit_flow_col, demand_zambia_col, demand_zimbabwe_col, eta=0.9, rho=1000, g=9.81, head=110.5):
    deficityears = []

    crit_dict = crit_data.set_index(year_col)[crit_flow_col].to_dict()
    demand_dict = crit_data.set_index(year_col)[[demand_zambia_col, demand_zimbabwe_col]].to_dict('index')

    for year, group in daily_data.groupby('hydro_year'):
        Q_crit = crit_dict.get(year)
        demand = demand_dict.get(year)

        if Q_crit is None or demand is None:
            continue

        group[flow_col] = pd.to_numeric(group[flow_col], errors='coerce')

        total_deficit = (Q_crit - group[flow_col]).clip(lower=0).sum()
        total_surplus = (group[flow_col] - Q_crit).clip(lower=0).sum()

        if total_deficit > total_surplus:
            avg_net_deficit = (total_deficit - total_surplus) / len(group)
            power_shortage_MW = (eta * rho * g * avg_net_deficit * head) / 1e6

            shared_shortage_MW = power_shortage_MW / 2

            shortage_pct_zambia = round(100 * shared_shortage_MW / demand[demand_zambia_col], 2)
            shortage_pct_zimbabwe = round(100 * shared_shortage_MW / demand[demand_zimbabwe_col], 2)

            deficityears.append({'hydro_year': year, 'avg_net_deficit_m^3/s': round(avg_net_deficit, 2), 'power_shortage_MW': round(power_shortage_MW, 2),
                'Zambia_shortage_%': shortage_pct_zambia, 'Zimbabwe_shortage_%': shortage_pct_zimbabwe})

    return pd.DataFrame(deficityears)

    
