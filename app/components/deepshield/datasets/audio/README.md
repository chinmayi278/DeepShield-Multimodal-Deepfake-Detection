# Audio intake

Manifest modality: audio. Group by speaker and original utterance/session; place all synthetic derivatives and codec variants in that group. FFmpeg decodes common supported containers to mono 16 kHz. Training uses a log-mel transfer baseline, not Dhwani weights or Dhwani architecture. Include real codec/noise/channel variation in evaluation; supply a separately licensed recording for background mixing. Preserve language/accent metadata and evaluate outside-language performance separately.
