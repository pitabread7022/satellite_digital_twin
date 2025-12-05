"""
Satellite Digital Twin - Mission Control Interface

Web-based simulation control and telemetry visualization.
Compliant with loads.md specification.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import (
    LoadsMDCompliantPolicy,
    BasicPolicy, 
    PowerSavePolicy, 
    HighPerformancePolicy, 
    CustomizablePolicy
)


def create_dashboard():
    """Initialize and render the mission control dashboard."""
    
    st.set_page_config(
        page_title="Satellite Digital Twin",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Professional styling
    st.markdown("""
        <style>
        .main-header {
            font-family: 'Courier New', monospace;
            color: #00ff00;
            background-color: #0a0a0a;
            padding: 10px;
            border: 1px solid #333;
        }
        .stMetric {
            background-color: #1a1a2e;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 10px;
        }
        .status-pass {
            color: #00ff00;
            font-weight: bold;
        }
        .status-fail {
            color: #ff0000;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("SATELLITE DIGITAL TWIN")
    st.markdown("**Mission Profile: 500km Sun-Synchronous Orbit | loads.md Compliant**")
    
    # Session state
    if 'simulation' not in st.session_state:
        st.session_state.simulation = None
    if 'history' not in st.session_state:
        st.session_state.history = []
    
    # Configuration sidebar
    with st.sidebar:
        st.header("CONFIGURATION")
        
        # Orbit Parameters
        with st.expander("Orbit Parameters", expanded=True):
            orbit_period = st.slider("Orbit Period [min]", 80, 110, 95)
            sunlight_duration = st.slider("Sunlight Duration [min]", 40, 70, 60)
            eclipse_duration = orbit_period - sunlight_duration
            st.text(f"Eclipse Duration: {eclipse_duration} min")
        
        # EPS
        with st.expander("Electrical Power System", expanded=True):
            solar_power = st.slider("Solar Array Power [W]", 40, 100, 60)
            battery_capacity = st.slider("Battery Capacity [Wh]", 50, 200, 100)
            st.text("Min SoC: 20% [CONSTRAINT]")
        
        # Load Budget
        with st.expander("Power Budget", expanded=True):
            st.markdown("**Load Profile:**")
            base_load = st.slider("Base Load [W]", 10, 25, 15)
            imaging_load = st.slider("Imaging Load [+W]", 30, 50, 40)
            downlink_load = st.slider("Downlink Load [+W]", 20, 40, 30)
            adcs_dump_load = st.slider("ADCS Dump Load [+W]", 5, 15, 10)
            
            st.markdown("**Operations Timing [per orbit]:**")
            imaging_duration = st.slider("Imaging Duration [min]", 5, 15, 10)
            downlink_duration = st.slider("Downlink Duration [min]", 5, 12, 8)
            adcs_dump_duration = st.slider("ADCS Dump Duration [min]", 3, 8, 5)
        
        # Data Budget
        with st.expander("Data Budget", expanded=False):
            data_per_orbit = st.slider("Data Generation [Gbit/orbit]", 1.0, 4.0, 2.0, 0.5)
            downlink_speed = st.slider("Downlink Rate [Mbps]", 20, 100, 50)
            max_storage = st.slider("Storage Capacity [GB]", 50, 500, 100)
            
            data_gb = data_per_orbit / 8.0
            dl_capacity = (downlink_speed / 8.0) * downlink_duration * 60 / 1000
            st.text(f"Data/orbit: {data_gb:.3f} GB")
            st.text(f"DL capacity: {dl_capacity:.2f} GB/pass")
        
        # Operational Windows
        with st.expander("Operational Windows", expanded=False):
            st.markdown("**Imaging Window [deg]:**")
            img_start = st.slider("Start Angle", 0, 180, 20)
            img_end = st.slider("End Angle", 20, 180, 60)
            
            st.markdown("**Ground Station Pass [deg]:**")
            gs_start = st.slider("GS Start", 60, 180, 95)
            gs_end = st.slider("GS End", 90, 200, 125)
            
            st.markdown("**ADCS Dump Window [deg]:**")
            adcs_start = st.slider("ADCS Start", 40, 120, 65)
            adcs_end = st.slider("ADCS End", 60, 140, 85)
        
        # Policy
        with st.expander("Operations Policy", expanded=True):
            policy_type = st.selectbox(
                "Policy Mode",
                ["Compliant", "Basic", "Power Save", "High Performance", "Custom"]
            )
            
            if policy_type == "Custom":
                custom_min_battery = st.slider("Min Battery for Ops [%]", 25, 80, 40)
        
        # Simulation
        with st.expander("Simulation Parameters", expanded=True):
            timestep = st.slider("Timestep [min]", 0.5, 5.0, 1.0, 0.5)
            duration_orbits = st.slider("Duration [orbits]", 1, 20, 5)
        
        # Initial State
        with st.expander("Initial Conditions", expanded=False):
            init_battery = st.slider("Initial SoC [%]", 30, 100, 80)
            init_data = st.slider("Initial Data [GB]", 0, 50, 0)
            init_angle = st.slider("Initial Orbit Angle [deg]", 0, 359, 0)
    
    # Build configuration
    config = SatelliteConfig(
        orbit_period_min=float(orbit_period),
        sunlight_duration_min=float(sunlight_duration),
        eclipse_duration_min=float(eclipse_duration),
        solar_panel_power_w=float(solar_power),
        battery_capacity_wh=float(battery_capacity),
        min_soc_percent=20.0,
        max_soc_percent=100.0,
        base_load_w=float(base_load),
        imaging_load_w=float(imaging_load),
        downlink_load_w=float(downlink_load),
        adcs_dump_load_w=float(adcs_dump_load),
        imaging_duration_min=float(imaging_duration),
        downlink_duration_min=float(downlink_duration),
        adcs_dump_duration_min=float(adcs_dump_duration),
        data_per_orbit_gbit=float(data_per_orbit),
        downlink_speed_mbps=float(downlink_speed),
        max_data_storage_gb=float(max_storage),
        imaging_windows_theta=[[float(img_start), float(img_end)]],
        ground_pass_window_theta=(float(gs_start), float(gs_end)),
        adcs_dump_window_theta=(float(adcs_start), float(adcs_end)),
        timestep_min=float(timestep)
    )
    
    # Policy selection
    if policy_type == "Compliant":
        policy = LoadsMDCompliantPolicy()
    elif policy_type == "Basic":
        policy = BasicPolicy()
    elif policy_type == "Power Save":
        policy = PowerSavePolicy()
    elif policy_type == "High Performance":
        policy = HighPerformancePolicy()
    else:
        policy = CustomizablePolicy(min_battery_imaging=custom_min_battery)
    
    # Initial state
    initial_state = SatelliteState(
        battery_level_percent=float(init_battery),
        battery_energy_wh=float(init_battery) * float(battery_capacity) / 100.0,
        onboard_data_volume_gb=float(init_data),
        orbit_angle_deg=float(init_angle),
        base_load_w=float(base_load),
        total_load_w=float(base_load)
    )
    
    # Control buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        run_button = st.button("EXECUTE SIMULATION", type="primary", use_container_width=True)
    with col2:
        if st.session_state.simulation:
            st.button("TRIGGER DOWNLINK", use_container_width=True)
    with col3:
        reset_button = st.button("RESET", use_container_width=True)
    
    if reset_button:
        st.session_state.simulation = None
        st.session_state.history = []
        st.rerun()
    
    if run_button:
        with st.spinner("Executing simulation..."):
            sim = Simulation(config, initial_state, policy)
            history = sim.run(duration_orbits=duration_orbits)
            st.session_state.simulation = sim
            st.session_state.history = history
        st.success(f"Simulation complete. {len(history)} timesteps executed.")
    
    # Results display
    if st.session_state.history:
        history = st.session_state.history
        sim = st.session_state.simulation
        summary = sim.get_summary()
        compliance = summary.get('compliance', {})
        
        # Compliance status
        st.markdown("---")
        if compliance.get('compliant', False):
            st.success("20% SoC CONSTRAINT: SATISFIED - Battery maintained above minimum threshold")
        else:
            st.error(f"20% SoC CONSTRAINT: VIOLATED - Minimum SoC reached: {compliance.get('min_soc_reached', 0):.1f}%")
        
        # Telemetry summary
        st.subheader("TELEMETRY SUMMARY")
        final_state = history[-1]
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            delta = final_state['battery_level_percent'] - history[0]['battery_level_percent']
            st.metric("Battery SoC", f"{final_state['battery_level_percent']:.1f}%",
                     delta=f"{delta:+.1f}%")
        
        with col2:
            st.metric("Min SoC", f"{compliance.get('min_soc_reached', 0):.1f}%")
        
        with col3:
            status = "SUNLIGHT" if final_state['in_sunlight'] else "ECLIPSE"
            st.metric("Illumination", status)
        
        with col4:
            st.metric("Total Load", f"{final_state['total_load_w']:.0f} W")
        
        with col5:
            st.metric("Data Volume", f"{final_state['onboard_data_volume_gb']:.3f} GB")
        
        with col6:
            st.metric("Orbit", f"{final_state['orbit_number']}")
        
        # Mode indicators
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if final_state.get('in_imaging_window', False):
                st.info("IMAGING WINDOW: ACTIVE")
            else:
                st.text("IMAGING WINDOW: INACTIVE")
        
        with col2:
            if final_state.get('in_ground_pass_window', False):
                st.info("GROUND CONTACT: ACTIVE")
            else:
                st.text("GROUND CONTACT: INACTIVE")
        
        with col3:
            if final_state.get('is_imaging', False):
                st.info("PAYLOAD: IMAGING")
            else:
                st.text("PAYLOAD: STANDBY")
        
        with col4:
            if final_state.get('is_downlinking', False):
                st.info("COMMS: TRANSMITTING")
            else:
                st.text("COMMS: IDLE")
        
        # Plots
        st.markdown("---")
        st.subheader("MISSION TELEMETRY")
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Overview", "Power System", "Power Budget", "Data System", "Compliance"
        ])
        
        df = pd.DataFrame(history)
        df['time_min'] = df['simulation_time_s'] / 60.0
        
        with tab1:
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.08,
                subplot_titles=('Battery State of Charge [%]', 'Power [W]', 'Data Volume [GB]')
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['battery_level_percent'],
                          mode='lines', name='SoC',
                          line=dict(color='#00cc00', width=2)),
                row=1, col=1
            )
            fig.add_hline(y=20, line_dash="dash", line_color="red", 
                         annotation_text="20% MIN", row=1, col=1)
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['solar_generation_w'],
                          mode='lines', name='Solar',
                          line=dict(color='#ffcc00', width=2)),
                row=2, col=1
            )
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['total_load_w'],
                          mode='lines', name='Load',
                          line=dict(color='#ff6600', width=2)),
                row=2, col=1
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['onboard_data_volume_gb'],
                          mode='lines', name='Data',
                          fill='tozeroy',
                          line=dict(color='#0066cc', width=2)),
                row=3, col=1
            )
            
            _add_eclipse_regions(fig, df)
            
            fig.update_layout(
                height=750,
                showlegend=True,
                template='plotly_dark',
                font=dict(family='Courier New')
            )
            fig.update_yaxes(title_text="SoC [%]", row=1, col=1, range=[0, 100])
            fig.update_yaxes(title_text="Power [W]", row=2, col=1)
            fig.update_yaxes(title_text="Data [GB]", row=3, col=1)
            fig.update_xaxes(title_text="Mission Elapsed Time [min]", row=3, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{"type": "scatter"}, {"type": "indicator"}],
                       [{"type": "scatter"}, {"type": "scatter"}]],
                subplot_titles=('SoC Timeline', 'Current SoC',
                              'Bus Voltage [V]', 'Net Power [W]')
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['battery_level_percent'],
                          mode='lines', line=dict(color='#00cc00', width=2)),
                row=1, col=1
            )
            
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number+delta",
                    value=final_state['battery_level_percent'],
                    delta={'reference': history[0]['battery_level_percent']},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': '#00cc00'},
                        'steps': [
                            {'range': [0, 20], 'color': "#660000"},
                            {'range': [20, 25], 'color': "#663300"},
                            {'range': [25, 100], 'color': "#1a1a2e"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 20
                        }
                    }
                ),
                row=1, col=2
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['battery_voltage_v'],
                          mode='lines', line=dict(color='#cc00cc', width=2)),
                row=2, col=1
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['net_power_w'],
                          mode='lines', fill='tozeroy',
                          line=dict(color='#0066cc', width=2)),
                row=2, col=2
            )
            
            fig.update_layout(height=600, showlegend=False, template='plotly_dark')
            st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['base_load_w'],
                mode='lines', name=f'Base [{base_load}W]',
                stackgroup='loads',
                line=dict(color='#0066cc')
            ))
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['payload_load_w'],
                mode='lines', name=f'Imaging [+{imaging_load}W]',
                stackgroup='loads',
                line=dict(color='#9900cc')
            ))
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['comms_load_w'],
                mode='lines', name=f'Downlink [+{downlink_load}W]',
                stackgroup='loads',
                line=dict(color='#00cc66')
            ))
            if 'adcs_dump_load_w' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['time_min'], y=df['adcs_dump_load_w'],
                    mode='lines', name=f'ADCS [+{adcs_dump_load}W]',
                    stackgroup='loads',
                    line=dict(color='#cc6600')
                ))
            
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['solar_generation_w'],
                mode='lines', name='Solar Generation',
                line=dict(color='#ffcc00', width=3, dash='dash')
            ))
            
            fig.update_layout(
                title='Power Budget Analysis [loads.md]',
                xaxis_title='Mission Elapsed Time [min]',
                yaxis_title='Power [W]',
                height=500,
                template='plotly_dark'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("**Power Modes [loads.md]:**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.text(f"Base:           {base_load} W")
                st.text(f"+ Imaging:      {base_load + imaging_load} W")
            with col2:
                st.text(f"+ Downlink:     {base_load + downlink_load} W")
                st.text(f"+ ADCS Dump:    {base_load + adcs_dump_load} W")
            with col3:
                st.text(f"Peak Load:      {base_load + imaging_load + adcs_dump_load} W")
        
        with tab4:
            col1, col2 = st.columns(2)
            
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df['time_min'], y=df['onboard_data_volume_gb'],
                    mode='lines', fill='tozeroy',
                    line=dict(color='#0066cc', width=2)
                ))
                fig.add_hline(y=max_storage, line_dash="dash", line_color="red")
                fig.update_layout(
                    title='Onboard Data Storage',
                    xaxis_title='Mission Elapsed Time [min]',
                    yaxis_title='Data Volume [GB]',
                    height=400,
                    template='plotly_dark'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("**Data Budget [loads.md]:**")
                data_stats = summary.get('data', {})
                st.metric("Generated", f"{data_stats.get('total_generated', 0):.3f} GB")
                st.metric("Downlinked", f"{data_stats.get('total_downlinked', 0):.3f} GB")
                st.metric("Onboard", f"{data_stats.get('final_stored', 0):.3f} GB")
                
                st.markdown("**Specification:**")
                st.text(f"Generation: {data_per_orbit} Gbit/orbit")
                st.text(f"Downlink:   {downlink_speed} Mbps")
        
        with tab5:
            st.subheader("20% SoC COMPLIANCE REPORT")
            
            report = sim.get_compliance_report()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Battery Compliance:**")
                soc_comp = report.get('soc_compliance', {})
                st.text(f"Requirement:    SoC >= 20%")
                st.text(f"Minimum SoC:    {soc_comp.get('min_soc_reached', 0):.1f}%")
                st.text(f"Violations:     {soc_comp.get('violations', 0)}")
                
                if soc_comp.get('compliant', False):
                    st.success("STATUS: COMPLIANT")
                else:
                    st.error("STATUS: NON-COMPLIANT")
            
            with col2:
                st.markdown("**Load Profile [loads.md]:**")
                load_prof = report.get('load_profile', {})
                st.text(f"Base Load:      {load_prof.get('base_load_w', 0)} W")
                st.text(f"Imaging:       +{load_prof.get('imaging_load_w', 0)} W")
                st.text(f"Downlink:      +{load_prof.get('downlink_load_w', 0)} W")
                st.text(f"ADCS Dump:     +{load_prof.get('adcs_dump_load_w', 0)} W")
            
            st.markdown("---")
            st.markdown("**Operations Timing [per orbit]:**")
            timing = report.get('timing_budget', {})
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Imaging", f"{timing.get('imaging_per_orbit_min', 0)} min")
            with col2:
                st.metric("Downlink", f"{timing.get('downlink_per_orbit_min', 0)} min")
            with col3:
                st.metric("ADCS Dump", f"{timing.get('adcs_dump_per_orbit_min', 0)} min")
        
        # Event log
        st.markdown("---")
        st.subheader("EVENT LOG")
        
        events = sim.get_events()
        if events:
            events_df = pd.DataFrame([
                {
                    'T+ [min]': f"{e.time_s/60:.1f}",
                    'SoC [%]': f"{e.battery_soc:.1f}",
                    'Event': e.event_type,
                    'Description': e.description
                }
                for e in events[-30:]
            ])
            st.dataframe(events_df, use_container_width=True)
        
        # Export
        st.markdown("---")
        st.subheader("DATA EXPORT")
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "DOWNLOAD CSV",
                df.to_csv(index=False),
                "telemetry.csv",
                "text/csv",
                use_container_width=True
            )
        with col2:
            import json
            st.download_button(
                "DOWNLOAD JSON",
                json.dumps(history, indent=2, default=str),
                "telemetry.json",
                "application/json",
                use_container_width=True
            )
    
    else:
        st.info("Configure parameters and execute simulation to view results.")
        
        st.markdown("---")
        st.subheader("LOADS.MD SPECIFICATION")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Power Budget:**")
            st.text(f"Base:        {base_load} W")
            st.text(f"Imaging:    +{imaging_load} W")
            st.text(f"Downlink:   +{downlink_load} W")
            st.text(f"ADCS Dump:  +{adcs_dump_load} W")
        
        with col2:
            st.markdown("**Timing [per orbit]:**")
            st.text(f"Imaging:     {imaging_duration} min")
            st.text(f"Downlink:    {downlink_duration} min")
            st.text(f"ADCS Dump:   {adcs_dump_duration} min")
        
        with col3:
            st.markdown("**Constraints:**")
            st.text("SoC >= 20% [STRICT]")
            st.text(f"Battery: {battery_capacity} Wh")
            st.text(f"Solar:   {solar_power} W")


def _add_eclipse_regions(fig, df):
    """Add eclipse shading to figure."""
    shapes = []
    in_eclipse = False
    eclipse_start = 0
    
    for i, row in df.iterrows():
        if not row['in_sunlight'] and not in_eclipse:
            eclipse_start = row['time_min']
            in_eclipse = True
        elif row['in_sunlight'] and in_eclipse:
            shapes.append(dict(
                type="rect", xref="x", yref="paper",
                x0=eclipse_start, x1=row['time_min'],
                y0=0, y1=1,
                fillcolor="#333333", opacity=0.3,
                layer="below", line_width=0
            ))
            in_eclipse = False
    
    if in_eclipse:
        shapes.append(dict(
            type="rect", xref="x", yref="paper",
            x0=eclipse_start, x1=df['time_min'].iloc[-1],
            y0=0, y1=1,
            fillcolor="#333333", opacity=0.3,
            layer="below", line_width=0
        ))
    
    fig.update_layout(shapes=shapes)


def run_dashboard():
    """Entry point."""
    create_dashboard()


if __name__ == "__main__":
    run_dashboard()
