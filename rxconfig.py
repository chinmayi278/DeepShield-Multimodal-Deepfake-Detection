import reflex as rx
import reflex_xy

config = rx.Config(
    app_name="app",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        reflex_xy.XYPlugin(),
    ],
)
