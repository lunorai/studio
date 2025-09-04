---
title: Vector
type: tags
order: 419
meta_title: Vector Tag for Adding Vectors to Images
meta_description: Customize Label Studio with the Vector tag by adding vectors to images for segmentation machine learning and data science projects.
---

The `Vector` tag is used to add vectors to an image without selecting a label.
This can be useful when you have only one label to assign to the vector. Use for
image segmentation tasks.

Use with the following data types: image.

{% insertmd includes/tags/vector.md %}

### Example

Basic labeling configuration for vector image segmentation

```html
<View>
    <Vector name="line-1" toName="img-1" />
    <Image name="img-1" value="$img" />
</View>
```
