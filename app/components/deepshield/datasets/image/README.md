# Image intake

Manifest modality: image. Store private RGB-decodable media under the configured dataset root. Record original source identity, generator/manipulation family, license, and all derived crops/recompressions in a common group. The loader checks dimensions before full decode and normalizes EXIF orientation. Binary labels must distinguish your chosen synthetic/manipulated target explicitly; generated-image and face-swap corpora are not interchangeable tasks.
