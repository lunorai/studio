---
title: VectorLabels
type: tags
order: 420
meta_title: Vector Label Tag for Labeling Vectors in Images
meta_description: Customize Label Studio with the VectorLabels tag and label vectors in images for semantic segmentation machine learning and data science projects.
---

The `VectorLabels` tag is used to create labeled vectors. Use to apply labels to
vectors in semantic segmentation tasks.

Use with the following data types: image.

{% insertmd includes/tags/vectorlabels.md %}

### Example

Basic labeling configuration for vector semantic segmentation of images

```html
<View>
    <Image name="image" value="$image" />
    <VectorLabels name="labels" toName="image">
        <label value="Road" /> <label value="Boundary" />
    </VectorLabels>
</View>
```
