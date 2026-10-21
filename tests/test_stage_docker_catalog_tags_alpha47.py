"""Focused tag alias proof: known catalog source must resolve to stage ID."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import stage_docker_api_broker as broker
from stage_host_socket import WUD_ID,WUD_SERVICE,WUD_IMAGE
from stage_store_compiler import EGRESS_PILOT_ID,EGRESS_PILOT_IMAGE
from stage_apps import AppError


class VerifiedCatalogAlias(unittest.TestCase):
    DIGEST="sha256:"+"a"*64
    OTHER="sha256:"+"b"*64

    def test_curated_wud_tag_only_on_exact_source_digest(self):
        correct=lambda ref:self.DIGEST if ref==WUD_IMAGE else None
        alias=broker._verified_catalog_tag(
            WUD_ID,WUD_SERVICE,self.DIGEST,resolver=correct)
        self.assertEqual(alias,"fmartinou/whats-up-docker:6.6.1")
        self.assertIsNone(broker._verified_catalog_tag(
            WUD_ID,WUD_SERVICE,self.OTHER,resolver=correct))
        self.assertIsNone(broker._verified_catalog_tag(
            WUD_ID,"wrong-service",self.DIGEST,resolver=correct))
        self.assertIsNone(broker._verified_catalog_tag(
            "default:Portainer",WUD_SERVICE,self.DIGEST,resolver=correct))
        with patch.object(broker,"resolve_image",
                          side_effect=AssertionError("not needed")):
            self.assertIsNone(broker._verified_catalog_tag(
                WUD_ID,WUD_SERVICE,self.OTHER,
                resolver=lambda ref:None))

    def test_same_image_shared_alias_only_from_fixed_catalog(self):
        alias="fmartinou/whats-up-docker:6.6.1"
        records=[
          {"Id":str(i)*64,"Image":alias,"ImageID":self.DIGEST,
           "Labels":{"osd.stage.scope":"staging-only",
                     "osd.stage.catalog.image_tag":alias}}
          for i in ("c","d")
        ]
        images=broker.stage_images(records)
        self.assertEqual(len(images),1)
        self.assertEqual(images[0]["Containers"],2)
        self.assertEqual(images[0]["RepoTags"],[alias])
        self.assertEqual(images[0]["RepoDigests"],[])
        self.assertEqual(images[0]["Labels"]["osd.stage.catalog.alias_source"],
                         "pinned_local_digest")
        self.assertNotIn("registry_password",json.dumps(images))
        invalid=[dict(records[0],Labels={
            "osd.stage.scope":"staging-only",
            "osd.stage.catalog.image_tag":"malicious/repository:latest"})]
        with self.assertRaises(AppError):
            broker.stage_images(invalid)
        records[1]["Labels"]={"osd.stage.scope":"staging-only"}
        records[1]["Image"]=self.DIGEST
        self.assertEqual(broker.stage_images(records)[0]["RepoTags"],[alias])

    def test_current_installed_stage_image_alias_has_exact_cached_digest(self):
        records=broker.stage_containers(fresh=True)
        self.assertTrue(records)
        images=broker.stage_images(records)
        approved=broker.PINNED_CATALOG_ALIASES
        for item in images:
            self.assertLessEqual(len(item["RepoTags"]),broker.MAX_CONTAINERS)
            self.assertTrue(set(item["RepoTags"]).issubset(approved))
            self.assertFalse(item["RepoDigests"])
        # Exact local cached tag may have been retargeted; never require a
        # presentation alias that no longer points at the running bytes.
        for record in records:
            alias=record["Labels"].get("osd.stage.catalog.image_tag")
            if alias is None:continue
            source=next(value for value in broker.PINNED_SOURCE_IMAGES.values()
                        if value.split("@sha256:",1)[0]==alias)
            self.assertEqual(broker.resolve_image(source),record["ImageID"])

    def test_mutated_tag_resolver_does_not_fabricate_display_version(self):
        self.assertIsNone(broker._verified_catalog_tag(
            EGRESS_PILOT_ID,"myspeed",self.DIGEST,
            resolver=lambda ref:self.OTHER))
        self.assertIsNone(broker._verified_catalog_tag(
            EGRESS_PILOT_ID,"myspeed",self.DIGEST,
            resolver=lambda ref:None))
        self.assertIsNone(broker._verified_catalog_tag(
            EGRESS_PILOT_ID,"myspeed",self.DIGEST,
            resolver=lambda ref:(_ for _ in ()).throw(AppError("missing",409))))


if __name__=="__main__":
    unittest.main()
