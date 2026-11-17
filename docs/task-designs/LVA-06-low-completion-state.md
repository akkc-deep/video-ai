# LVA-06 results

One actual quality/strict/serial/libx264 matrix shared by baseline and final.

| Batch | Wall seconds | Human union | Non-human envelope | Cost / usable second |
|---|---:|---:|---:|---:|

Trial envelopes overlap and include queueing. Local warm P50/P95 are separate.
Historical microbenchmarks are not causal end-to-end gains. Full-film throughput is unverified.

```json
{
  "task_id": "LVA-06",
  "fixture": "low",
  "root": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low",
  "plan_sha256": "220c087ed0a5a94ac8f5e1ff263dda522871ca6fb3424ca37efdf2c3474d7758",
  "status": "quality_accepted",
  "pending_review": null,
  "review": [],
  "summary": {
    "schema_version": 1,
    "task_id": "LVA-06",
    "profile": "quality_strict_serial_x264",
    "matrix_count": 1,
    "report_identities": {
      "baseline": "new_actual_quality_matrix",
      "final": "new_actual_quality_matrix"
    },
    "batches": [
      {
        "batch_id": "low",
        "mode": "normal",
        "batch_wall_seconds": 9407.4489300251,
        "human_wait_seconds": 6911.003233909607,
        "non_human_envelope_seconds": 2496.445696115494,
        "active_span_seconds": 2472.0895490646362,
        "idle_other_waiting_seconds": 24.356147050857544,
        "trial_scheduling_envelopes_seconds": [
          9395.305110692978,
          9399.35182762146,
          9403.408470630646,
          9407.446397542953
        ],
        "envelope_scope": "Overlapping trial envelopes include batch queueing; never sum for throughput.",
        "accepted_video_seconds": 23.25,
        "cost_per_usable_video_second": 107.374008435075,
        "cost_missing_reason": null,
        "quality_decisions": [
          {
            "kind": "native",
            "start": 1794832937.7349317,
            "end": 1794839848.7381656,
            "decision": "accepted",
            "decision_artifact": {
              "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\reviews\\native-user-decision.json",
              "bytes": 3484,
              "sha256": "cdf8649ed83e889d810aceee5bebb08c35a8031a9781db78f5147c10054467e3"
            },
            "media_artifacts": [
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\output\\low_motion\\cold_1_00001_.mp4",
                "bytes": 1547941,
                "sha256": "c4bf59bddde03bb582e850b5a1289d96005ccd3a84bd3c6c03664a1973cd716f"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\cold_1\\retained.mp4",
                "bytes": 1410621,
                "sha256": "b9466c910edf6452bda2c8e9320fbcfccb24a25110476ff5fe19ea7128236f71"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\cold_1\\frame_000093.png",
                "bytes": 352522,
                "sha256": "cf024c37ddf62c1bd79defb15b320fbce6a6db980fcdbafb8d0394ce5da348a8"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\output\\low_motion\\warm_1_00001_.mp4",
                "bytes": 1547941,
                "sha256": "4019297dd331029961058c1ae67606adf6c95b4c790401f48927ff59e9c47cb9"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\warm_1\\retained.mp4",
                "bytes": 1410621,
                "sha256": "b9466c910edf6452bda2c8e9320fbcfccb24a25110476ff5fe19ea7128236f71"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\warm_1\\frame_000093.png",
                "bytes": 352522,
                "sha256": "cf024c37ddf62c1bd79defb15b320fbce6a6db980fcdbafb8d0394ce5da348a8"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\output\\low_motion\\warm_2_00001_.mp4",
                "bytes": 1547941,
                "sha256": "0d2385ecb94e95892c8a10e32ca0aba155ac46099742133950009a669617005f"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\warm_2\\retained.mp4",
                "bytes": 1410621,
                "sha256": "b9466c910edf6452bda2c8e9320fbcfccb24a25110476ff5fe19ea7128236f71"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\warm_2\\frame_000093.png",
                "bytes": 352522,
                "sha256": "cf024c37ddf62c1bd79defb15b320fbce6a6db980fcdbafb8d0394ce5da348a8"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\output\\low_motion\\warm_3_00001_.mp4",
                "bytes": 1547941,
                "sha256": "e916bbfd6da509fac7b757afcbd53d435623e1fed2f70436c591733c4fc0da6e"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\warm_3\\retained.mp4",
                "bytes": 1410621,
                "sha256": "b9466c910edf6452bda2c8e9320fbcfccb24a25110476ff5fe19ea7128236f71"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\native_low\\trials\\warm_3\\frame_000093.png",
                "bytes": 352522,
                "sha256": "cf024c37ddf62c1bd79defb15b320fbce6a6db980fcdbafb8d0394ce5da348a8"
              }
            ]
          },
          {
            "kind": "final",
            "start": 1794840357.5190382,
            "end": 1794843519.8044214,
            "decision": "accepted",
            "decision_artifact": {
              "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\reviews\\final-user-decision.json",
              "bytes": 1494,
              "sha256": "582f6499bb22a61152f50fb4740e1d4b08205e52800228869c2eb69baae99425"
            },
            "media_artifacts": [
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\upscale\\postprocess\\low_motion_cold_1\\candidate-1080p.mp4",
                "bytes": 5854912,
                "sha256": "6c141c85511b18c62ff298f893e28ad4aaa7658ec49283ab0ca6d2d85c56a337"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\upscale\\postprocess\\low_motion_warm_1\\candidate-1080p.mp4",
                "bytes": 5854912,
                "sha256": "6c141c85511b18c62ff298f893e28ad4aaa7658ec49283ab0ca6d2d85c56a337"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\upscale\\postprocess\\low_motion_warm_2\\candidate-1080p.mp4",
                "bytes": 5854912,
                "sha256": "6c141c85511b18c62ff298f893e28ad4aaa7658ec49283ab0ca6d2d85c56a337"
              },
              {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\upscale\\postprocess\\low_motion_warm_3\\candidate-1080p.mp4",
                "bytes": 5854912,
                "sha256": "6c141c85511b18c62ff298f893e28ad4aaa7658ec49283ab0ca6d2d85c56a337"
              }
            ]
          }
        ],
        "stages": [
          {
            "name": "native_low",
            "trial": null,
            "start": 1794830950.040781,
            "end": 1794832937.7110274,
            "active_seconds": 1987.6678976000112,
            "evidence": {
              "receipt": {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\stage-results\\native_low.json",
                "bytes": 35242,
                "sha256": "a8dd6a58361fd87a05b1aee4d76c3438f4f7ee366960eef9cd4c8863fef570ad"
              }
            }
          },
          {
            "name": "upscale_low",
            "trial": null,
            "start": 1794839873.0473907,
            "end": 1794840340.259424,
            "active_seconds": 467.20826959999977,
            "evidence": {
              "receipt": {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\stage-results\\upscale_low.json",
                "bytes": 964074,
                "sha256": "f7508c2e887b9d619805c38ecaaf596b94fa7a867474fec98b9812e4eb8754da"
              }
            }
          },
          {
            "name": "composition",
            "trial": "cold_1",
            "start": 1794840340.2614245,
            "end": 1794840345.3366845,
            "active_seconds": 5.072160600015195,
            "evidence": {
              "receipt": {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\stage-results\\composition_cold_1.json",
                "bytes": 65141,
                "sha256": "6085be024daa794299e64b4b1de899bf046d21549e5796860a06d1934ed0c99c"
              }
            }
          },
          {
            "name": "composition",
            "trial": "warm_1",
            "start": 1794840345.3391867,
            "end": 1794840349.3834014,
            "active_seconds": 4.041244199994253,
            "evidence": {
              "receipt": {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\stage-results\\composition_warm_1.json",
                "bytes": 65140,
                "sha256": "dbc722ad07491cb9131c225ff28951ed466e7192434923173fc047fde18b890d"
              }
            }
          },
          {
            "name": "composition",
            "trial": "warm_2",
            "start": 1794840349.3861806,
            "end": 1794840353.4400444,
            "active_seconds": 4.0513746999786235,
            "evidence": {
              "receipt": {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\stage-results\\composition_warm_2.json",
                "bytes": 65142,
                "sha256": "9fa102c554a06987ed1ccb6e76a8c099172eb5ed10ca7855b3104e869aefafcb"
              }
            }
          },
          {
            "name": "composition",
            "trial": "warm_3",
            "start": 1794840353.4440403,
            "end": 1794840357.4779713,
            "active_seconds": 4.031882899987977,
            "evidence": {
              "receipt": {
                "path": "E:\\VideoAI\\scratch\\benchmarks\\LVA-06-20261116-072639-e2a8e6-low\\stage-results\\composition_warm_3.json",
                "bytes": 65142,
                "sha256": "34ce54de8b87989979e557aba87c725e0aaebcd5b8c326832a1a2d23e03ba4e4"
              }
            }
          }
        ],
        "resources": {
          "low": {
            "node_calls": {
              "wan.vae_loader": 1,
              "wan.image_load": 1,
              "wan.text_loader": 1,
              "wan.text_encode": 2,
              "wan.image_conditioning": 1,
              "wan.model_loader": 2,
              "wan.high_sample": 4,
              "wan.low_sample": 4,
              "wan.vae_decode": 4,
              "wan.video_prepare": 4,
              "wan.encode": 4
            },
            "node_cpu_wall_seconds": {
              "wan.vae_loader": 0.08460339999874122,
              "wan.image_load": 0.014534699992509559,
              "wan.text_loader": 0.34632879999116994,
              "wan.text_encode": 1.819672800018452,
              "wan.image_conditioning": 2.2025043000176083,
              "wan.model_loader": 0.10484120002365671,
              "wan.high_sample": 690.6608246000251,
              "wan.low_sample": 1148.6264434999903,
              "wan.vae_decode": 12.245265000034124,
              "wan.video_prepare": 9.940000018104911e-05,
              "wan.encode": 2.51708890000009
            },
            "model_method_calls": {
              "comfy.model_load": 15
            },
            "model_method_cpu_wall_seconds": {
              "comfy.model_load": 0.5188321999739856
            },
            "physical_model_load_count": null,
            "device_sampled_peak_vram_mib": 22046,
            "device_mean_gpu_utilization_percent": 95.41904761904762,
            "gpu_samples": 945,
            "malformed_events": 0,
            "backend": "native Comfy ImageUpscaleWithModel / RealESRGAN",
            "scope": "Method/node CPU wall intervals and device-wide samples, not kernel time, physical transfers or exclusive-process peaks.",
            "device_low_utilization": {
              "threshold_percent": 5,
              "max_sample_gap_seconds": 6,
              "intervals": [
                {
                  "start_seconds": 0.049123500008136034,
                  "end_seconds": 55.13326160001452,
                  "samples": 26
                },
                {
                  "start_seconds": 523.5070053999953,
                  "end_seconds": 527.6031982999993,
                  "samples": 3
                },
                {
                  "start_seconds": 701.3272949999955,
                  "end_seconds": 701.3272949999955,
                  "samples": 1
                },
                {
                  "start_seconds": 991.7038203999982,
                  "end_seconds": 995.7928925000015,
                  "samples": 3
                },
                {
                  "start_seconds": 1462.0653298000107,
                  "end_seconds": 1466.1610644999892,
                  "samples": 3
                },
                {
                  "start_seconds": 1930.3867871999973,
                  "end_seconds": 1934.4819600000046,
                  "samples": 3
                }
              ],
              "observed_span_seconds": 71.4603105999995,
              "scope": "Adjacent device-wide samples, including desktop/startup; not exclusive or kernel idle."
            },
            "service_result": {
              "returncode": 0,
              "timed_out": false,
              "metrics_finalized": true,
              "wall_seconds": 1961.6718391999893,
              "observed_peak_process_rss_bytes": 5781794816,
              "rss_samples": 1948,
              "physical_model_load_count": null
            },
            "retained_logical_file_bytes": 36041986,
            "peak_logical_file_bytes": null,
            "disk_scope": "Retained file lengths at phase end; filesystem/temp peak not sampled, no files deleted for benefit."
          },
          "upscale": {
            "node_calls": {
              "wan.image_load": 372,
              "upscale.model_loader": 1,
              "upscale.inference": 372
            },
            "node_cpu_wall_seconds": {
              "wan.image_load": 4.844191899930593,
              "upscale.model_loader": 0.18012350000208244,
              "upscale.inference": 208.3591313001525
            },
            "model_method_calls": {
              "comfy.model_load": 372
            },
            "model_method_cpu_wall_seconds": {
              "comfy.model_load": 28.369773399754195
            },
            "physical_model_load_count": null,
            "device_sampled_peak_vram_mib": 6450,
            "device_mean_gpu_utilization_percent": 35.776649746192895,
            "gpu_samples": 197,
            "malformed_events": 0,
            "backend": "native Comfy ImageUpscaleWithModel / RealESRGAN",
            "scope": "Method/node CPU wall intervals and device-wide samples, not kernel time, physical transfers or exclusive-process peaks.",
            "device_low_utilization": {
              "threshold_percent": 5,
              "max_sample_gap_seconds": 6,
              "intervals": [
                {
                  "start_seconds": 0.049649099993985146,
                  "end_seconds": 26.798398199985968,
                  "samples": 12
                },
                {
                  "start_seconds": 30.881988899986027,
                  "end_seconds": 41.09729360000347,
                  "samples": 6
                },
                {
                  "start_seconds": 47.240806999994675,
                  "end_seconds": 55.503450099990005,
                  "samples": 5
                },
                {
                  "start_seconds": 59.59984290000284,
                  "end_seconds": 61.64399099998991,
                  "samples": 2
                },
                {
                  "start_seconds": 65.74081680001109,
                  "end_seconds": 76.19483990001027,
                  "samples": 6
                },
                {
                  "start_seconds": 88.47236869999324,
                  "end_seconds": 90.51509609998902,
                  "samples": 2
                },
                {
                  "start_seconds": 98.71945100001176,
                  "end_seconds": 98.71945100001176,
                  "samples": 1
                },
                {
                  "start_seconds": 102.81555020000087,
                  "end_seconds": 104.85369849999552,
                  "samples": 2
                },
                {
                  "start_seconds": 113.0268694999977,
                  "end_seconds": 115.07127359998412,
                  "samples": 2
                },
                {
                  "start_seconds": 119.16949569998542,
                  "end_seconds": 119.16949569998542,
                  "samples": 1
                },
                {
                  "start_seconds": 143.89980109999306,
                  "end_seconds": 154.1165469000116,
                  "samples": 6
                },
                {
                  "start_seconds": 160.25847030000295,
                  "end_seconds": 160.25847030000295,
                  "samples": 1
                },
                {
                  "start_seconds": 164.36249609998777,
                  "end_seconds": 168.44630270000198,
                  "samples": 3
                },
                {
                  "start_seconds": 174.57505379998474,
                  "end_seconds": 180.7102736000088,
                  "samples": 4
                },
                {
                  "start_seconds": 207.25747079998837,
                  "end_seconds": 215.42023429999244,
                  "samples": 5
                },
                {
                  "start_seconds": 229.72824130000663,
                  "end_seconds": 231.76905060000718,
                  "samples": 2
                },
                {
                  "start_seconds": 235.85072660000878,
                  "end_seconds": 241.99689999999828,
                  "samples": 4
                },
                {
                  "start_seconds": 246.09444399998756,
                  "end_seconds": 246.09444399998756,
                  "samples": 1
                },
                {
                  "start_seconds": 252.228716099984,
                  "end_seconds": 254.26523260000977,
                  "samples": 2
                },
                {
                  "start_seconds": 262.44918110000435,
                  "end_seconds": 264.5007312000089,
                  "samples": 2
                },
                {
                  "start_seconds": 268.59955029998673,
                  "end_seconds": 276.7609397000051,
                  "samples": 5
                },
                {
                  "start_seconds": 299.2526545999863,
                  "end_seconds": 319.6941525999864,
                  "samples": 11
                },
                {
                  "start_seconds": 340.29712939998717,
                  "end_seconds": 360.73201889998745,
                  "samples": 11
                },
                {
                  "start_seconds": 381.33066889998736,
                  "end_seconds": 399.71107059999486,
                  "samples": 10
                },
                {
                  "start_seconds": 405.8468889000069,
                  "end_seconds": 405.8468889000069,
                  "samples": 1
                }
              ],
              "observed_span_seconds": 172.14191150007537,
              "scope": "Adjacent device-wide samples, including desktop/startup; not exclusive or kernel idle."
            },
            "service_result": {
              "returncode": 0,
              "timed_out": false,
              "metrics_finalized": true,
              "wall_seconds": 430.6762574999884,
              "observed_peak_process_rss_bytes": 1499938816,
              "rss_samples": 428,
              "physical_model_load_count": null
            },
            "retained_logical_file_bytes": 1560032493,
            "peak_logical_file_bytes": null,
            "disk_scope": "Retained file lengths at phase end; filesystem/temp peak not sampled, no files deleted for benefit."
          }
        },
        "counters": {
          "decode": 24,
          "actual_sha_bytes": 6592026217,
          "probe": 28,
          "producer": 16,
          "post": 376,
          "get": 2494,
          "actual_sha_calls": 10184
        },
        "failed": 0,
        "redone": 0,
        "counters_complete": true,
        "counter_scope": "Direct coordinator invocation deltas, accumulated once per completed stage; interrupted invocation missing counts explicit."
      }
    ],
    "local_groups": [
      {
        "batch_id": "low",
        "stage": "native_low",
        "mode": "normal",
        "temperature": "process_cold",
        "samples": 1,
        "p50_seconds": 472.22541779998573,
        "p95_seconds": 472.22541779998573,
        "scope": "local stage only; three warm observations are descriptive"
      },
      {
        "batch_id": "low",
        "stage": "native_low",
        "mode": "normal",
        "temperature": "warm_process",
        "samples": 3,
        "p50_seconds": 469.1846108000027,
        "p95_seconds": 469.47288503000163,
        "scope": "local stage only; three warm observations are descriptive"
      },
      {
        "batch_id": "low",
        "stage": "upscale_low",
        "mode": "normal",
        "temperature": "process_cold",
        "samples": 1,
        "p50_seconds": 91.34265290011535,
        "p95_seconds": 91.34265290011535,
        "scope": "local stage only; three warm observations are descriptive"
      },
      {
        "batch_id": "low",
        "stage": "upscale_low",
        "mode": "normal",
        "temperature": "warm_process",
        "samples": 3,
        "p50_seconds": 92.3858231001359,
        "p95_seconds": 93.15801832987054,
        "scope": "local stage only; three warm observations are descriptive"
      }
    ],
    "attribution": {
      "defaults": [
        {
          "item": "quality/strict/serial/libx264 medium CRF18",
          "source": "docs/task-designs/LVA-05-completion.json",
          "new_gain": false
        },
        {
          "item": "historical capability cache, batch extraction/copy, single AV decode",
          "source": "docs/task-designs/video-generation-performance-results.md",
          "new_gain": false
        }
      ],
      "experimental": [
        {
          "item": "validation candidate",
          "adopted": false,
          "source": "docs/task-designs/LVA-02-results.json"
        },
        {
          "item": "bounded preparation",
          "adopted": false,
          "source": "docs/task-designs/LVA-03-results.json"
        },
        {
          "item": "prefetch/writeback mixed local observations; parent writeback 1.56%",
          "adopted": false,
          "source": "docs/task-designs/LVA-05-gpu-results.json"
        }
      ],
      "rejected": [
        {
          "item": "distill native mixed diff/diff_b/diff_m incompatibility",
          "source": "docs/task-designs/LVA-04-completion.json"
        },
        {
          "item": "NVENC RGB differs in 93/93 frames",
          "source": "docs/task-designs/LVA-05-completion.json"
        }
      ],
      "unverified": [
        "Sage/cache/compile unsupported or unverified",
        "combined I/O not run",
        "107-scene full-film throughput",
        "physical weight transfers, kernel/exclusive idle"
      ]
    },
    "full_film_throughput": null,
    "causal_speedup": null,
    "historical_comparison": "LVA-01 separate timing/environment/scheduling; no causal before/after ratio"
  },
  "invocation_counters": {
    "post": 0,
    "get": 0,
    "producer": 0,
    "decode": 0,
    "probe": 0,
    "actual_sha_calls": 0,
    "actual_sha_bytes": 0
  },
  "production_resumed": false
}
```
