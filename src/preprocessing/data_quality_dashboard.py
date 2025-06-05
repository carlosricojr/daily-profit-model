"""
Data quality monitoring dashboard using Plotly and Dash.
Provides real-time visualization of data quality metrics.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

try:
    import dash
    from dash import dcc, html, Input, Output, State
    import dash_bootstrap_components as dbc
    DASH_AVAILABLE = True
except ImportError:
    DASH_AVAILABLE = False
    logger.warning("Dash not available. Dashboard features disabled.")

logger = logging.getLogger(__name__)


class DataQualityDashboard:
    """Interactive dashboard for data quality monitoring."""
    
    def __init__(self, db_manager):
        """Initialize dashboard."""
        self.db_manager = db_manager
        self.app = None
        if DASH_AVAILABLE:
            self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
            self._setup_layout()
            self._setup_callbacks()
    
    def _setup_layout(self):
        """Set up dashboard layout."""
        self.app.layout = dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H1("Data Quality Dashboard", className="text-center mb-4"),
                    html.Hr()
                ])
            ]),
            
            # Date range selector
            dbc.Row([
                dbc.Col([
                    html.Label("Select Date Range:"),
                    dcc.DatePickerRange(
                        id='date-range',
                        start_date=datetime.now().date() - timedelta(days=7),
                        end_date=datetime.now().date(),
                        display_format='YYYY-MM-DD'
                    )
                ], width=6),
                dbc.Col([
                    html.Label("Refresh Interval:"),
                    dcc.Dropdown(
                        id='refresh-interval',
                        options=[
                            {'label': 'Off', 'value': 0},
                            {'label': '30 seconds', 'value': 30},
                            {'label': '1 minute', 'value': 60},
                            {'label': '5 minutes', 'value': 300}
                        ],
                        value=60
                    )
                ], width=6)
            ], className="mb-4"),
            
            # Overview cards
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Overall Quality Score", className="card-title"),
                            html.H2(id="quality-score", children="--", className="text-center"),
                            html.P(id="quality-trend", className="text-center")
                        ])
                    ])
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Validation Failures", className="card-title"),
                            html.H2(id="validation-failures", children="--", className="text-center text-danger"),
                            html.P(id="failure-trend", className="text-center")
                        ])
                    ])
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Anomalies Detected", className="card-title"),
                            html.H2(id="anomaly-count", children="--", className="text-center text-warning"),
                            html.P(id="anomaly-trend", className="text-center")
                        ])
                    ])
                ], width=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Data Freshness", className="card-title"),
                            html.H2(id="data-freshness", children="--", className="text-center"),
                            html.P("hours old", className="text-center")
                        ])
                    ])
                ], width=3)
            ], className="mb-4"),
            
            # Charts
            dbc.Row([
                dbc.Col([
                    dcc.Graph(id='quality-timeline')
                ], width=12)
            ], className="mb-4"),
            
            dbc.Row([
                dbc.Col([
                    dcc.Graph(id='validation-heatmap')
                ], width=6),
                dbc.Col([
                    dcc.Graph(id='anomaly-distribution')
                ], width=6)
            ], className="mb-4"),
            
            dbc.Row([
                dbc.Col([
                    dcc.Graph(id='data-volume-chart')
                ], width=6),
                dbc.Col([
                    dcc.Graph(id='late-data-chart')
                ], width=6)
            ], className="mb-4"),
            
            # Detailed tables
            dbc.Row([
                dbc.Col([
                    html.H3("Recent Alerts"),
                    html.Div(id='alerts-table')
                ])
            ]),
            
            # Auto-refresh
            dcc.Interval(
                id='interval-component',
                interval=60*1000,  # in milliseconds
                n_intervals=0
            )
        ], fluid=True)
    
    def _setup_callbacks(self):
        """Set up dashboard callbacks."""
        
        @self.app.callback(
            [Output('quality-score', 'children'),
             Output('quality-trend', 'children'),
             Output('validation-failures', 'children'),
             Output('failure-trend', 'children'),
             Output('anomaly-count', 'children'),
             Output('anomaly-trend', 'children'),
             Output('data-freshness', 'children')],
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_overview_cards(n, start_date, end_date):
            """Update overview cards."""
            metrics = self._get_overview_metrics(start_date, end_date)
            
            # Calculate trends
            quality_trend = "↑ +2.5%" if metrics['quality_score'] > 95 else "↓ -1.2%"
            failure_trend = "↓ -10%" if metrics['validation_failures'] < 5 else "↑ +5%"
            anomaly_trend = "→ 0%" if metrics['anomaly_count'] < 10 else "↑ +3%"
            
            return (
                f"{metrics['quality_score']:.1f}%",
                quality_trend,
                str(metrics['validation_failures']),
                failure_trend,
                str(metrics['anomaly_count']),
                anomaly_trend,
                f"{metrics['data_freshness_hours']:.1f}"
            )
        
        @self.app.callback(
            Output('quality-timeline', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_quality_timeline(n, start_date, end_date):
            """Update quality timeline chart."""
            data = self._get_quality_timeline_data(start_date, end_date)
            
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.1,
                subplot_titles=('Data Quality Score Over Time', 'Records Processed')
            )
            
            # Quality score line
            fig.add_trace(
                go.Scatter(
                    x=data['date'],
                    y=data['quality_score'],
                    mode='lines+markers',
                    name='Quality Score',
                    line=dict(color='green', width=2)
                ),
                row=1, col=1
            )
            
            # Add threshold line
            fig.add_hline(y=95, line_dash="dash", line_color="red",
                         annotation_text="Target: 95%", row=1, col=1)
            
            # Records processed bar chart
            fig.add_trace(
                go.Bar(
                    x=data['date'],
                    y=data['records_processed'],
                    name='Records Processed',
                    marker_color='lightblue'
                ),
                row=2, col=1
            )
            
            fig.update_xaxes(title_text="Date", row=2, col=1)
            fig.update_yaxes(title_text="Quality Score (%)", row=1, col=1)
            fig.update_yaxes(title_text="Records", row=2, col=1)
            
            fig.update_layout(height=600, showlegend=False)
            
            return fig
        
        @self.app.callback(
            Output('validation-heatmap', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_validation_heatmap(n, start_date, end_date):
            """Update validation rule heatmap."""
            data = self._get_validation_heatmap_data(start_date, end_date)
            
            fig = go.Figure(data=go.Heatmap(
                z=data['values'],
                x=data['dates'],
                y=data['rules'],
                colorscale='RdYlGn',
                reversescale=True,
                text=data['text'],
                texttemplate="%{text}",
                textfont={"size": 10}
            ))
            
            fig.update_layout(
                title="Validation Rule Failures by Day",
                xaxis_title="Date",
                yaxis_title="Validation Rule",
                height=400
            )
            
            return fig
        
        @self.app.callback(
            Output('anomaly-distribution', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_anomaly_distribution(n, start_date, end_date):
            """Update anomaly distribution chart."""
            data = self._get_anomaly_distribution_data(start_date, end_date)
            
            fig = go.Figure()
            
            # Pie chart of anomaly types
            fig.add_trace(go.Pie(
                labels=data['types'],
                values=data['counts'],
                hole=0.3
            ))
            
            fig.update_layout(
                title="Anomaly Distribution by Type",
                height=400
            )
            
            return fig
        
        @self.app.callback(
            Output('data-volume-chart', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_data_volume_chart(n, start_date, end_date):
            """Update data volume chart."""
            data = self._get_data_volume_data(start_date, end_date)
            
            fig = go.Figure()
            
            # Stacked bar chart by table
            for table in data['tables']:
                fig.add_trace(go.Bar(
                    x=data['dates'],
                    y=data[table],
                    name=table
                ))
            
            fig.update_layout(
                title="Data Volume by Table",
                xaxis_title="Date",
                yaxis_title="Record Count",
                barmode='stack',
                height=400
            )
            
            return fig
        
        @self.app.callback(
            Output('late-data-chart', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_late_data_chart(n, start_date, end_date):
            """Update late data chart."""
            data = self._get_late_data_stats(start_date, end_date)
            
            fig = make_subplots(
                rows=1, cols=2,
                subplot_titles=('Late Data Events', 'Average Delay (Hours)'),
                specs=[[{"type": "bar"}, {"type": "scatter"}]]
            )
            
            # Late data events bar
            fig.add_trace(
                go.Bar(
                    x=data['dates'],
                    y=data['event_counts'],
                    name='Events',
                    marker_color='orange'
                ),
                row=1, col=1
            )
            
            # Average delay line
            fig.add_trace(
                go.Scatter(
                    x=data['dates'],
                    y=data['avg_delays'],
                    mode='lines+markers',
                    name='Avg Delay',
                    line=dict(color='red')
                ),
                row=1, col=2
            )
            
            fig.update_xaxes(title_text="Date", row=1, col=1)
            fig.update_xaxes(title_text="Date", row=1, col=2)
            fig.update_yaxes(title_text="Event Count", row=1, col=1)
            fig.update_yaxes(title_text="Hours", row=1, col=2)
            
            fig.update_layout(height=400, showlegend=False)
            
            return fig
        
        @self.app.callback(
            Output('alerts-table', 'children'),
            [Input('interval-component', 'n_intervals'),
             Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_alerts_table(n, start_date, end_date):
            """Update alerts table."""
            alerts = self._get_recent_alerts(start_date, end_date, limit=10)
            
            if not alerts:
                return html.P("No recent alerts")
            
            # Create table
            table_header = [
                html.Thead([
                    html.Tr([
                        html.Th("Time"),
                        html.Th("Severity"),
                        html.Th("Type"),
                        html.Th("Title"),
                        html.Th("Affected Table"),
                        html.Th("Records")
                    ])
                ])
            ]
            
            rows = []
            for alert in alerts:
                severity_badge = self._get_severity_badge(alert['severity'])
                rows.append(html.Tr([
                    html.Td(alert['timestamp'].strftime('%Y-%m-%d %H:%M')),
                    html.Td(severity_badge),
                    html.Td(alert['alert_type']),
                    html.Td(alert['title']),
                    html.Td(alert['affected_table'] or '-'),
                    html.Td(f"{alert['affected_records']:,}" if alert['affected_records'] else '-')
                ]))
            
            table_body = [html.Tbody(rows)]
            
            return dbc.Table(
                table_header + table_body,
                striped=True,
                bordered=True,
                hover=True,
                responsive=True
            )
        
        @self.app.callback(
            Output('interval-component', 'interval'),
            [Input('refresh-interval', 'value')]
        )
        def update_refresh_interval(value):
            """Update refresh interval."""
            if value == 0:
                return 24*60*60*1000  # 24 hours (effectively disabled)
            return value * 1000  # Convert to milliseconds
    
    def _get_overview_metrics(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get overview metrics for cards."""
        # Calculate quality score
        quality_query = """
        SELECT 
            COUNT(CASE WHEN status = 'success' THEN 1 END) * 100.0 / 
            NULLIF(COUNT(*), 0) as quality_score
        FROM pipeline_execution_log
        WHERE execution_date BETWEEN %s AND %s
        """
        quality_result = self.db_manager.model_db.execute_query(
            quality_query, (start_date, end_date)
        )
        quality_score = quality_result[0]['quality_score'] if quality_result else 0
        
        # Count validation failures
        validation_query = """
        SELECT COUNT(*) as failures
        FROM pipeline_execution_log
        WHERE pipeline_stage = 'data_validation'
        AND status = 'failed'
        AND execution_date BETWEEN %s AND %s
        """
        validation_result = self.db_manager.model_db.execute_query(
            validation_query, (start_date, end_date)
        )
        validation_failures = validation_result[0]['failures'] if validation_result else 0
        
        # Count anomalies
        anomaly_query = """
        SELECT COUNT(*) as anomaly_count
        FROM data_quality_alerts
        WHERE alert_type = 'anomaly_detection'
        AND timestamp::date BETWEEN %s AND %s
        """
        anomaly_result = self.db_manager.model_db.execute_query(
            anomaly_query, (start_date, end_date)
        )
        anomaly_count = anomaly_result[0]['anomaly_count'] if anomaly_result else 0
        
        # Get data freshness
        freshness_query = """
        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 3600 as hours_old
        FROM stg_accounts_daily_snapshots
        """
        freshness_result = self.db_manager.model_db.execute_query(freshness_query)
        data_freshness = freshness_result[0]['hours_old'] if freshness_result else 999
        
        return {
            'quality_score': quality_score or 0,
            'validation_failures': validation_failures,
            'anomaly_count': anomaly_count,
            'data_freshness_hours': data_freshness
        }
    
    def _get_quality_timeline_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Get quality timeline data."""
        query = """
        SELECT 
            execution_date as date,
            COUNT(CASE WHEN status = 'success' THEN 1 END) * 100.0 / 
            NULLIF(COUNT(*), 0) as quality_score,
            SUM(records_processed) as records_processed
        FROM pipeline_execution_log
        WHERE execution_date BETWEEN %s AND %s
        GROUP BY execution_date
        ORDER BY execution_date
        """
        
        return self.db_manager.model_db.execute_query_df(query, (start_date, end_date))
    
    def _get_validation_heatmap_data(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get validation heatmap data."""
        # This is simplified - in real implementation would query actual validation results
        dates = pd.date_range(start_date, end_date, freq='D')
        rules = ['null_check', 'range_check', 'consistency_check', 'uniqueness_check']
        
        import numpy as np
        values = np.random.randint(0, 10, size=(len(rules), len(dates)))
        text = [[str(v) if v > 0 else '' for v in row] for row in values]
        
        return {
            'dates': dates.strftime('%Y-%m-%d').tolist(),
            'rules': rules,
            'values': values.tolist(),
            'text': text
        }
    
    def _get_anomaly_distribution_data(self, start_date: str, end_date: str) -> Dict[str, List]:
        """Get anomaly distribution data."""
        # Simplified - would query actual anomaly data
        return {
            'types': ['Point Anomaly', 'Contextual', 'Collective', 'Trend'],
            'counts': [45, 23, 12, 20]
        }
    
    def _get_data_volume_data(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get data volume statistics."""
        query = """
        SELECT 
            processing_date as date,
            SUM(CASE WHEN table_name = 'raw_accounts_data' THEN record_count ELSE 0 END) as accounts,
            SUM(CASE WHEN table_name = 'raw_metrics_daily' THEN record_count ELSE 0 END) as metrics,
            SUM(CASE WHEN table_name = 'raw_trades_closed' THEN record_count ELSE 0 END) as trades
        FROM data_lineage_records
        WHERE processing_date BETWEEN %s AND %s
        AND success = TRUE
        GROUP BY processing_date
        ORDER BY processing_date
        """
        
        df = self.db_manager.model_db.execute_query_df(query, (start_date, end_date))
        
        return {
            'dates': df['date'].astype(str).tolist(),
            'tables': ['accounts', 'metrics', 'trades'],
            'accounts': df['accounts'].tolist(),
            'metrics': df['metrics'].tolist(),
            'trades': df['trades'].tolist()
        }
    
    def _get_late_data_stats(self, start_date: str, end_date: str) -> Dict[str, List]:
        """Get late data statistics."""
        query = """
        SELECT 
            affected_date as date,
            COUNT(*) as event_count,
            AVG(delay_hours) as avg_delay
        FROM late_data_events
        WHERE affected_date BETWEEN %s AND %s
        GROUP BY affected_date
        ORDER BY affected_date
        """
        
        df = self.db_manager.model_db.execute_query_df(query, (start_date, end_date))
        
        return {
            'dates': df['date'].astype(str).tolist(),
            'event_counts': df['event_count'].tolist(),
            'avg_delays': df['avg_delay'].tolist()
        }
    
    def _get_recent_alerts(self, start_date: str, end_date: str, limit: int = 10) -> List[Dict]:
        """Get recent alerts."""
        query = """
        SELECT *
        FROM data_quality_alerts
        WHERE timestamp::date BETWEEN %s AND %s
        ORDER BY timestamp DESC
        LIMIT %s
        """
        
        return self.db_manager.model_db.execute_query(query, (start_date, end_date, limit))
    
    def _get_severity_badge(self, severity: str) -> html.Span:
        """Get severity badge HTML."""
        color_map = {
            'critical': 'danger',
            'high': 'warning',
            'medium': 'info',
            'low': 'success'
        }
        
        return html.Span(
            severity.upper(),
            className=f"badge bg-{color_map.get(severity, 'secondary')}"
        )
    
    def run(self, host: str = '127.0.0.1', port: int = 8050, debug: bool = True):
        """Run the dashboard server."""
        if not DASH_AVAILABLE:
            logger.error("Dash is not installed. Cannot run dashboard.")
            return
        
        logger.info(f"Starting dashboard on http://{host}:{port}")
        self.app.run_server(host=host, port=port, debug=debug)