# Texture Coordinates for UsdSolid B-reps

Copyright &copy; 2026, NVIDIA Corporation, version 0.1 (DRAFT)

Jens Jebens

## Contents

- [Summary](#summary)
- [Problem statement](#problem-statement)
- [Proposed schema: BrepTexCoordAPI](#proposed-schema-breptexcoordapi)
- [Evaluation rules](#evaluation-rules)
- [Example](#example)
- [Authoring maps](#authoring-maps)
- [Validation](#validation)
- [Alternatives considered](#alternatives-considered)
- [Excluded topics](#excluded-topics)
- [Open questions](#open-questions)
- [Relationship to other proposals](#relationship-to-other-proposals)
- [Prior art](#prior-art)
- [Appendix: AI-assisted drafting](#appendix-ai-assisted-drafting)

## Summary

This proposal adds texture coordinates to the UsdSolid B-rep schema proposed in [OpenUSD-proposals #109, *Solid Models in USD*](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/109). Each texture coordinate set is a map, authored per face, from the face's surface parameters (u, v) to texture coordinates (s, t). Any tessellation of the B-rep evaluates the map at its vertices and authors the result as a face-varying `texCoord2f[]` primvar. Every tessellation therefore places a texture the same way, whatever its chord height, and the exact B-rep remains the single source of truth for both shape and texture placement.

The extension is one multiple-apply API schema, `BrepTexCoordAPI`, with two map types:

- `affine`: six coefficients per face. This is enough for planes, for analytic cylinders, and for CAD surface mappings defined as a linear transform of the surface parameters.
- `bspline`: a polynomial B-spline over the face's parameter domain. This is for NURBS and other freeform faces, and for layouts fitted from an existing mesh.

## Problem statement

A B-rep face is a trimmed region of a surface S(u, v), and every point on the face has surface parameters. The UsdSolid schema records the parameter domain of each face (`face:range`) and its trim curves (`BrepCurveUvNurbAPI`), but defines no texture coordinates. A textured material bound to a `UsdSolidBrepArray`, directly or through a `GeomSubset`, therefore has no coordinates to read unless the tessellator invents them, and two tessellators that do so can place the same texture differently.

Surface parameters cannot serve as `st` directly:

- A NURBS surface's parameters are knot values with no physical unit, and they are not proportional to arc length, so equal parameter steps cover unequal distances on the surface.
- The analytic surface types planned in the UsdSolid proposal's geometry type extensions mix units. A plane's parameters are lengths; a cylinder's are an angle in radians and an axial length.
- The direction of u on each face depends on how the face was modelled.

A texture coordinate set therefore needs a map per face from (u, v) to (s, t). Two workflows depend on it:

- **Texture placement that survives re-tessellation.** A consumer derives display meshes from a B-rep at whatever fidelity it needs, and the UsdSolid proposal lists relating a B-rep to its tessellated derivatives as an open question. `st` authored on a derived mesh is lost when the mesh is regenerated, and each level of detail (LOD) needs its own unwrap or transfer.
- **Meshes rebuilt as B-reps.** A textured mesh, such as a SimReady asset, rebuilt as a native B-rep loses its authored UV layout. A per-face map fitted to the source mesh's `st` keeps that layout at every LOD tessellated from the B-rep.

## Proposed schema: BrepTexCoordAPI

`BrepTexCoordAPI` is a multiple-apply API schema with the property namespace prefix `brep`, applied to a `UsdSolidBrepArray`. The instance name is the name of the primvar a tessellation authors: `BrepTexCoordAPI:st` produces `primvars:st`. Its attributes follow the UsdSolid proposal's packing conventions: arrays are packed across all Breps in the array, records of each map type are stored in face order, and geometry is double precision. The snippet uses that proposal's preliminary `PrelimUsdSolid` prefix.

```usda
class "BrepTexCoordAPI" (
    inherits = </APISchemaBase>
    doc = """Texture coordinates for the faces of a BrepArray, defined per face as a map
    from the face's surface parameters (u, v) to texture coordinates (s, t). A tessellation
    evaluates the map at each vertex and authors a face-varying texCoord2f[] primvar named
    after the instance."""
    customData = { token apiSchemaType = "multipleApply"
                   token propertyNamespacePrefix = "brep"
                   token[] apiSchemaCanOnlyApplyTo = ["PrelimUsdSolidBrepArray"]
                 }
)
{
    uniform token[] texCoord:mapType (
        allowedTokens = ["none", "affine", "bspline"]
        doc = """face_ii's map type. size() = number of faces.
        none    = face_ii has no coordinates in this set.
        affine  = s and t are affine functions of (u, v); see texCoord:affine:s and :t.
        bspline = (s, t) is a polynomial B-spline function of (u, v); see texCoord:bspline:*."""
        customData = { string apiName = "texCoordMapType" }
    )

    uniform double3[] texCoord:affine:s (
        doc = """packed coefficients (a, b, c) giving s = a*u + b*v + c, one entry per face
        whose mapType is affine, in face order. size() = number of affine faces."""
        customData = { string apiName = "texCoordAffineS" }
    )
    uniform double3[] texCoord:affine:t (
        doc = """packed coefficients (a, b, c) giving t = a*u + b*v + c, parallel to
        texCoord:affine:s."""
        customData = { string apiName = "texCoordAffineT" }
    )

    uniform texCoord2d[] texCoord:bspline:controlValues (
        doc = """packed (s, t) control values of all bspline maps, in face order. The layout
        is row-major with U as rows and V as columns, as in BrepSurfaceNurbAPI.
        size() = SUM_ii(uVertexCount[ii] * vVertexCount[ii])."""
        customData = { string apiName = "texCoordBsplineControlValues" }
    )
    uniform uint[] texCoord:bspline:uOrder           # size() = number of bspline faces
    uniform uint[] texCoord:bspline:vOrder
    uniform uint[] texCoord:bspline:uVertexCount
    uniform uint[] texCoord:bspline:vVertexCount
    uniform double[] texCoord:bspline:uKnots         # per-map slice = uOrder + uVertexCount
    uniform double[] texCoord:bspline:vKnots         # per-map slice = vOrder + vVertexCount
}
```

The `bspline` map is non-rational: a fitted texture layout has no need for weights, and evaluation stays a plain tensor-product sum.

## Evaluation rules

A consumer that tessellates a `UsdSolidBrepArray` with `BrepTexCoordAPI:<name>` applied:

1. Authors `primvars:<name>` on the derived mesh, or emits it in Hydra, as `texCoord2f[]` with `faceVarying` interpolation.
2. Gives each face-vertex the value of the map of the face its polygon lies on, evaluated at that vertex's (u, v) on that face. A vertex on an edge shared by two faces receives one value per face.
3. Uses the (u, v) at which it placed the vertex in the face's parameter domain, and does not re-project the 3D point onto the surface. On a closed surface, the corners of each polygon then lie on one side of the seam. At a pole or apex, each corner keeps the parameters of its own polygon.
4. Evaluates the map in the parameterisation that `face:range` and `BrepCurveUvNurbAPI` use: the knot domain for NURBS surfaces, and for the analytic surface types the PRC/STEP parameterisation, with angles in radians and axial height for cones. A kernel that tessellates in another parameterisation converts each vertex's parameters before evaluating, as it already does for `face:range`.
5. Authors the primvar as indexed when any face has `mapType` `none`, and points the corners of those faces at the primvar's `unauthoredValuesIndex`.

Material binding is unchanged. Per-face and per-Brep materials bind through `GeomSubset` as the UsdSolid proposal describes. A texture reader selects the set by primvar name, for example a `UsdPrimvarReader_float2` with `varname = "st"`.

## Example

A roller on a millimetre stage: face 0 is the side, a cylinder of radius 35, and faces 1 and 2 are planar end caps. The example uses the analytic surface types of the geometry type extensions, as implemented in [jensjebens/OpenUSD PR 61](https://github.com/jensjebens/OpenUSD/pull/61). The map places one texture repeat every 10 mm on all three faces. Arc length around the side is 35 u for u in radians, so s = 3.5 u. On the caps, u and v are lengths, so s = 0.1 u and t = 0.1 v.

```usda
def BrepArray "Roller" (
    prepend apiSchemas = ["BrepSurfaceCylinderAPI", "BrepSurfacePlaneAPI", "BrepTexCoordAPI:st"]
)
{
    # topology and surface geometry as in the UsdSolid proposal's cube example

    uniform token[] brep:st:texCoord:mapType = ["affine", "affine", "affine"]
    uniform double3[] brep:st:texCoord:affine:s = [(3.5, 0, 0), (0.1, 0, 0), (0.1, 0, 0)]
    uniform double3[] brep:st:texCoord:affine:t = [(0, 0.1, 0), (0, 0.1, 0), (0, 0.1, 0)]
}
```

Any tessellation of `Roller` authors `texCoord2f[] primvars:st (interpolation = "faceVarying")`. A checker texture then shows square 10 mm checks on the side and on the caps at every chord height.

## Authoring maps

A writer expresses every map in the parameterisation of evaluation rule 4.

- **Physically scaled maps for tiling materials.** With k = `metersPerUnit` divided by the texture's repeat length in metres:
  - plane: s = k u, t = k v;
  - analytic cylinder of radius r: s = k r u, t = k v.

  Both are exact affine maps. Cones, spheres and tori have no exact affine map at uniform scale, so a writer either accepts the distortion of an affine map or fits a `bspline` map to arc length within a chosen tolerance. The same applies to a cylinder stored as a rational NURBS surface, as the UsdSolid proposal currently requires: no rational parameterisation of a circle is proportional to arc length, so its physically scaled map is a fitted `bspline`.
- **CAD imports.** A CAD surface mapping defined as a linear transform of surface parameters converts to `affine`. Projection mappings (planar, box, cylindrical, spherical) do not convert, because they depend on 3D position rather than on (u, v).
- **Meshes rebuilt as B-reps.** The rebuild fits each face's map to the source mesh's `st`, sampled at the points of the source mesh closest to points on the face. It uses `affine` where that fit is within tolerance and `bspline` otherwise. A smooth per-face map can reproduce a layout only inside one UV island, so the rebuild places face boundaries along the source mesh's UV seams.

## Validation

The UsdSolid validation rules gain these checks for each applied instance:

- `texCoord:mapType` has one entry per face.
- `texCoord:affine:s` and `texCoord:affine:t` each have one entry per `affine` face.
- The `bspline` count arrays have one entry per `bspline` face. Each map satisfies the coherent-NURBS rules (positive order not exceeding the vertex count, a knot vector of size order + vertex count, non-decreasing). `controlValues` has the summed size.
- Each `bspline` map's knot domain contains its face's `face:range`.

## Alternatives considered

- **Primvars authored on the `UsdSolidBrepArray` itself.** USD's interpolation modes are defined for meshes, curves and patches, and none of them assigns values over B-rep faces and their parameter domains. The closest, `uniform`, would hold one value per face, which cannot place a texture across it.
- **`st` on derived display meshes only.** The coordinates are lost whenever a mesh is regenerated, every LOD needs its own transfer, and the B-rep stops being the source of truth for the asset.
- **Per-control-point `st` on the surface.** `UsdGeomNurbsPatch` evaluates `vertex`-interpolated primvars with the surface's own basis. Analytic surfaces have no control points, though, and the map's resolution would be tied to the surface's.
- **Projection map types.** Planar, box and triplanar projections are functions of 3D position, and shading networks already provide them at render time.

## Excluded topics

- Texture transforms within a material (`UsdTransform2d`), which stay in the shading network.
- Continuity of `st` across shared edges. A writer that needs continuity authors matching maps on adjacent faces; a validation rule for it can follow.
- Rational maps.
- Tangent frames for normal maps, which renderers derive from `st`.

## Open questions

1. Whether instance names should follow a convention such as `st`, `st1`, and so on.
2. The value type of `bspline` control values: `texCoord2d[]` to match the schema's double precision, or `texCoord2f[]` to match the primvar the tessellation authors.
3. Whether `none` is needed at all, or every face of an applied instance must have a map.

## Relationship to other proposals

- [OpenUSD-proposals #109, *Solid Models in USD*](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/109) defines the schema this proposal extends. Its geometry type extensions add the analytic surface types the `affine` examples rely on.
- The UsdSolid proposal defers relating a B-rep to its tessellated derivatives to follow-up work, pointing to its companion problem statement, [OpenUSD-proposals #108](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/108). With texture coordinates defined on the B-rep, that correlation mechanism does not have to carry UV data when it is designed.

## Prior art

- **Rhino.** The default surface mapping follows each face's parameters, and the openNURBS file format stores it as a linear transform of the surface parameters ([Rhino 8 texture mapping](https://docs.mcneel.com/rhino/8/help/en-us/properties/texturemapping.htm), [opennurbs_texture_mapping.h](https://github.com/mcneel/opennurbs/blob/8.x/opennurbs_texture_mapping.h)).
- **PRC (ISO 14739-1).** PRC defines a "Parametric" texture mapping type, which HOOPS Exchange lists as reserved for future use ([A3DETextureMappingType](https://docs.techsoft3d.com/hoops/exchange/api/c/enums/A3DETextureMappingType.html)).
- **STEP AP242 and JT.** Both store texture coordinates on tessellated geometry only ([single_texture_style_tessellation_specification](https://www.steptools.com/stds/stp_aim/html/t_single_texture_style_tessellation_specification.html), [JT v10 file format reference](https://www.plm.automation.siemens.com/en_us/Images/JT-v10-file-format-reference-rev-B_tcm1023-233786.pdf)).
- **CAD-to-real-time pipelines.**
  - PiXYZ tessellates with `ConformalScaledUV`, one undistorted island per B-rep face ([UV pipeline](https://docs.unity.com/en-us/asset-transformer-sdk/2026.1/manual/functions/uv-pipeline)).
  - HOOPS Exchange's `KeepUV` keeps the parametric points as texture coordinates ([getting tessellation](https://docs.techsoft3d.com/exchange/latest/guide/geometry/getting_tessellation.html)).
- **Kernels.** Open CASCADE stores a (u, v) on every triangulation node ([Poly_Triangulation](https://github.com/Open-Cascade-SAS/OCCT/blob/master/src/FoundationClasses/TKMath/Poly/Poly_Triangulation.hxx)). SMLib's tessellator records the surface (u, v) of every polygon corner. Tessellators built on either kernel therefore have the parameters these rules need.
- **USD.** The primvar interpolation modes, including the evaluation of `vertex` primvars with a patch's basis, are documented in [UsdGeomPrimvar](https://openusd.org/release/api/class_usd_geom_primvar.html).

## Appendix: AI-assisted drafting

This proposal was drafted with the assistance of an AI language model (Claude, Anthropic) operating within Claude Code, under the direction of Jens Jebens. All conceptual framing, editorial decisions and technical judgment are the responsibility of the human author. The context provided to the AI comprised the UsdSolid proposal and its implementation in jensjebens/OpenUSD, the usd-brep 1.0.1 source, and a survey of how CAD applications, kernels and exchange formats handle texture coordinates.
