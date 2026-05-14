import unittest

from app.services.video_probe import VideoProbeService


class VideoProbeServiceTest(unittest.TestCase):
    def test_parse_hdr10_video_payload(self):
        payload = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 3840,
                    "height": 2160,
                    "bit_rate": "24900000",
                    "duration": "7200.5",
                    "avg_frame_rate": "24000/1001",
                    "color_transfer": "smpte2084",
                    "pix_fmt": "yuv420p10le",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "truehd",
                    "channels": 8,
                    "tags": {"language": "eng"},
                },
            ],
            "format": {"bit_rate": "30000000"},
        }

        result = VideoProbeService()._parse_payload(payload)

        self.assertEqual(result["video_width"], 3840)
        self.assertEqual(result["video_height"], 2160)
        self.assertEqual(result["video_codec"], "hevc")
        self.assertEqual(result["video_bitrate"], 24900000)
        self.assertEqual(result["video_dynamic_range"], "HDR10")
        self.assertEqual(result["video_bit_depth"], 10)
        self.assertAlmostEqual(result["video_fps"], 23.976)
        self.assertEqual(result["audio_tracks"], [{"codec": "truehd", "language": "eng", "channels": "8"}])

    def test_parse_dolby_vision_from_side_data(self):
        payload = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 3840,
                    "height": 2160,
                    "avg_frame_rate": "24/1",
                    "side_data_list": [{"side_data_type": "DOVI configuration record"}],
                }
            ]
        }

        result = VideoProbeService()._parse_payload(payload)

        self.assertEqual(result["video_dynamic_range"], "Dolby Vision")
        self.assertEqual(result["video_fps"], 24.0)


if __name__ == "__main__":
    unittest.main()
