### Parameters

| Param | Type | Default | Description |
| --- | --- | --- | --- |
| name | <code>string</code> |  | Name of tag |
| toName | <code>string</code> |  | Name of image to label |
| [choice] | <code>single</code> \| <code>multiple</code> | <code>single</code> | Configure whether you can select one or multiple labels |
| [maxUsages] | <code>number</code> |  | Maximum number of times a label can be used per task |
| [showInline] | <code>boolean</code> | <code>true</code> | Show labels in the same visual line |
| [opacity] | <code>number</code> | <code>0.2</code> | Opacity of vector |
| [fillColor] | <code>string</code> |  | Vector fill color in hexadecimal |
| [strokeColor] | <code>string</code> |  | Stroke color in hexadecimal |
| [strokeWidth] | <code>number</code> | <code>1</code> | Width of stroke |
| [pointSize] | <code>small</code> \| <code>medium</code> \| <code>large</code> | <code>medium</code> | Size of vector handle points |
| [pointStyle] | <code>rectangle</code> \| <code>circle</code> | <code>rectangle</code> | Style of points |
| [snap] | <code>pixel</code> \| <code>none</code> | <code>none</code> | Snap vector to image pixels |

### Result parameters

**Kind**: global typedef  
**Returns**: [<code>VectorRegionResult</code>](#VectorRegionResult) - The serialized vector region data in Label Studio format  
**Properties**

| Name | Type | Description |
| --- | --- | --- |
| original_width | <code>number</code> | width of the original image (px) |
| original_height | <code>number</code> | height of the original image (px) |
| image_rotation | <code>number</code> | rotation degree of the image (deg) |
| value | <code>Object</code> |  |
| value.vertices | <code>Array.&lt;Object&gt;</code> | array of point objects with coordinates, bezier curve information, and point relationships |
| value.closed | <code>boolean</code> | whether the vector is closed (polygon) or open (polyline) |
| value.vectorlabels | <code>Array.&lt;string&gt;</code> | array of label names assigned to this vector |

### Example JSON
```json
{
  "original_width": 1920,
  "original_height": 1280,
  "image_rotation": 0,
  "value": {
    "vertices": [
      { "id": "point-1", "x": 25.0, "y": 30.0, "prevPointId": null, "isBezier": false },
      { "id": "point-2", "x": 75.0, "y": 70.0, "prevPointId": "point-1", "isBezier": true,
        "controlPoint1": {"x": 50.0, "y": 40.0}, "controlPoint2": {"x": 60.0, "y": 60.0} }
    ],
    "closed": false,
    "vectorlabels": ["Road"]
  }
}
```

