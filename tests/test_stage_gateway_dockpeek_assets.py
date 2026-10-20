"""One targeted rewrite regression for the real Dockpeek staging HTML."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from stage_app_gateway import rewrite,parse_route
from stage_apps import AppError


class GatewayDockpeek(unittest.TestCase):
    PROJECT="osd-compiled-c2b7884e9d2d"

    def test_rewrite_only_selected_project_routes(self):
        origin=(b'<link href="/static/css/tailwindcss.css">'
                b'<script src="/static/js/app.js"></script>'
                b'<a href="/export/json">download</a>'
                b'<a href="/logout">Logout</a>'
                b'<script>fetch("/api/containers")</script>')
        result=rewrite(origin,"text/html",self.PROJECT).decode()
        prefix="/stage-app/"+self.PROJECT+"/"
        for suffix in ("static/css/tailwindcss.css","static/js/app.js",
                       "export/json","logout","api/containers"):
            self.assertIn(prefix+suffix,result)
            project,route=parse_route(prefix+suffix)
            self.assertEqual((project,route),(self.PROJECT,"/"+suffix))
        self.assertNotIn('href="/static/',result)
        self.assertNotIn('src="/static/',result)

    def test_no_rewrite_json_or_non_html(self):
        body=b'{"path":"/static/js/app.js"}'
        self.assertEqual(rewrite(body,"application/json",self.PROJECT),body)


if __name__=="__main__":
    unittest.main()
