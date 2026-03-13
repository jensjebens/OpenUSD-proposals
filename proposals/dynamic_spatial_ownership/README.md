# Dynamic Spatial Ownership in Composed Scenes

Copyright &copy; 2026, NVIDIA Corporation, version 0.1 (DRAFT)

Jens Jebens, Aaron Luk

## Contents

- [Introduction](#introduction)
- [Motivation](#motivation)
  - [How USD handles spatial relationships today](#how-usd-handles-spatial-relationships-today)
  - [The expanding ecosystem](#the-expanding-ecosystem)
- [Problem statement](#problem-statement)
  - [Three modes of spatial ownership](#three-modes-of-spatial-ownership)
  - [Why scene graphs cannot express dynamic ownership](#why-scene-graphs-cannot-express-dynamic-ownership)
  - [Why this matters now](#why-this-matters-now)
- [Existing mechanisms in USD](#existing-mechanisms-in-usd)
  - [Prim hierarchy and transform inheritance](#prim-hierarchy-and-transform-inheritance)
  - [UsdGeomPointInstancer](#usdgeompointinstancer)
  - [Relationships and constraints](#relationships-and-constraints)
  - [Namespace editing and relocates](#namespace-editing-and-relocates)
- [Industry use cases](#industry-use-cases)
  - [Manufacturing and logistics](#manufacturing-and-logistics)
  - [Media and Entertainment](#media-and-entertainment)
  - [Robotics and simulation](#robotics-and-simulation)
- [Prior art](#prior-art)
  - [Discrete event simulation](#discrete-event-simulation)
  - [Entity-relationship models (IFC)](#entity-relationship-models-ifc)
- [Design considerations](#design-considerations)
  - [Principles](#principles)
  - [Open questions and tradeoffs](#open-questions-and-tradeoffs)
  - [Tradeoff summary](#tradeoff-summary)
  - [Risks](#risks)
- [Relationship to other proposals](#relationship-to-other-proposals)
- [Next steps](#next-steps)
- [Appendix A: AI-Assisted Drafting](#appendix-a-ai-assisted-drafting)

## Introduction

In any system that uses a hierarchical scene graph -- USD, glTF, FBX,
Alembic, game engine scene trees, CAD assembly structures -- spatial
relationships are expressed through hierarchy: when a parent moves, its
children move with it. This works when parent-child structure is fixed.
It breaks down when objects change parents over time.

That change is what this proposal calls *dynamic spatial ownership.* It
arises whenever objects move between carriers: parts moving through a
factory, characters picking up props in a film, cargo transferring
between vehicles in a logistics simulation. The domain vocabulary
changes; the structural problem does not.

**Expected outcome.** This proposal seeks community alignment on the
structure of the dynamic ownership problem -- distinguishing three modes
of spatial ownership that practitioners frequently collapse into one.
The industries where USD is now finding adoption -- manufacturing,
logistics, AECO, robotics -- designed their own data models around
dynamic relationships because those relationships are fundamental to
their workflows. As USD enters these industries, this need arrives with
the content. This proposal defines the problem, presents the tradeoffs,
and identifies what must be understood before any mechanism can be
proposed.

## Motivation

### How USD handles spatial relationships today

OpenUSD's prim hierarchy is the sole mechanism for spatial parenting.
When an ancestor prim moves, its descendants move with it. A prim's
namespace path -- and therefore its parent -- is the same at every time
code. This invariance is deliberate: stable paths enable caching,
composition, deterministic playback, and non-destructive overrides.

There is no USD mechanism to express: "this object is parented to the
robot from frame 0--100 and to the AGV from frame 101 onward."
Transforms can vary over time, but the set of spatial relationships --
which prim is a child of which parent -- cannot. Changing that structure
requires namespace editing (`UsdNamespaceEditor`, relocates), an authoring-layer
operation that is neither animatable nor runtime-triggerable.

### The expanding ecosystem

USD was born in visual effects and animation, where parent-child
relationships are typically fixed within a shot or sequence. A character
rig has a stable joint hierarchy; a set has a stable spatial structure.
Dynamic parenting exists (props attached to characters, vehicles carrying passengers)
but is usually handled through DCC-specific constraint systems that do not
serialize into USD.

As USD expands into new domains, it increasingly encounters workflows
where dynamic spatial ownership is not an edge case but the dominant mode
of operation:

- **Factory and logistics simulation** assembles thousands of parts
  through hundreds of stations. Every part changes carriers many times.
  The dynamic relationships *are* the simulation.
- **Robotics** requires objects to attach to and detach from grippers,
  conveyors, and mobile platforms at runtime. Physics must remain
  consistent across each transition.
- **Construction simulation** tracks materials moving through laydown
  areas, cranes, hoists, and installation positions.
- **Film and game production** involves characters picking up, throwing,
  and dropping objects. DCC tools handle these transitions through
  constraint rigs that are baked into USD as time-sampled transforms --
  a workflow that works at shot scale but discards the dynamic
  relationships from the scene description. Another tool reading the
  published USD cannot recover which character held which prop at which
  time without re-deriving it from the baked transforms.

In all these cases, the workarounds are the same: bake world-space transforms
(losing hierarchy), pre-place copies and toggle visibility (prim explosion), or
flatten into point instancers (losing identity). Each team invents its own
combination. None express the dynamic relationships that the simulation actually
computes.

## Problem statement

### Three modes of spatial ownership

When objects move through a physical process, their motion is governed by
different mechanisms at different times. Understanding these modes -- and
their combinations -- is essential for scoping the problem correctly.

**Animation.** An object's position is driven by pre-authored or
procedurally generated transforms that are a function of time. A bottle
sliding along a conveyor, a car body advancing through a paint booth, a
lantern swinging across a ship's deck in a storm. Animation does not
require hierarchy -- the motion can be expressed in world space -- but
without hierarchy, every object needs its own transform data, even when
many objects are moving as a rigid group on the same carrier.

**Parenting.** An object's position is derived from the transform of
another object -- its "parent." A gripper holding a part, a pallet
carrying stacked boxes, a character's hand gripping a sword. Parenting is
what hierarchy was designed for -- and where its static nature becomes a
limitation.

**Simulation.** An object's position is determined by a physics engine
responding to forces, collisions, and constraints. A part falling off a
conveyor, boxes settling under gravity after being stacked, rubble
separating from a collapsing wall.

**These modes overlap.** A part can be parented and animated
simultaneously (attached to a robot arm following a joint animation while
the part rotates locally), parented and simulated (boxes on an AGV
shifting under physics during transport), or transitioning between modes
(animated along a conveyor, then parented to a gripper, then released
into physics simulation). The transition between modes -- especially the
moment of handoff -- is where the hardest problems lie.

### Why scene graphs cannot express dynamic ownership

The workarounds practitioners adopt -- world-space baking, visibility
toggling, over-flattening into vectorized representations -- each
sacrifice something that a proper solution would preserve:

- **World-space baking** preserves visual correctness but loses the
  semantic information that the object was "attached to the robot" vs.
  "on the AGV." Every object needs a full transform at every frame.
- **Visibility toggling** preserves hierarchy but requires pre-authoring
  every carrier-object combination and does not represent a single
  persistent object. Prim count scales with the product of objects and
  carriers.
- **Over-flattening** (point instancers, particle systems) solves the
  data and prim scaling problems but objects lose individual identity,
  cannot carry per-instance overrides, and are invisible to subsystems
  that operate on the scene graph (physics, clash detection, selection,
  queries).

Each workaround is a response to the same gap: scene graphs express
*what is related to what* but not *when those relationships change.*

Hierarchy is one way to express spatial relationships, but not the only
one -- and not always sufficient. Discrete event simulators decouple
logical ownership from spatial hierarchy because objects change carriers
continuously (see [Prior art](#prior-art)). Entity-relationship standards
like IFC express containment, aggregation, and connection through
explicit relationship objects because buildings require richer spatial
semantics than parent-child hierarchy can capture. In both cases, the
industries built their data models around relationships that hierarchy
alone cannot represent. As USD finds adoption in these industries, the
content arriving at USD's door carries an implicit requirement for
relationship types that USD's hierarchy does not currently express.

However, any mechanism for USD must reckon with the properties that
hierarchy provides: stable namespace paths enable identification,
addressability, composition, and non-destructive overrides. These are
load-bearing guarantees. The challenge is to determine whether dynamic
ownership can be expressed without disturbing these invariants, and what
the real costs and benefits are. That determination requires both
cross-industry input on where the problem is most acute and prototype
evidence on what works at scale.

### Why this matters now

1. **Factory-scale simulation is here.** The workarounds that work at 10
   objects do not work at 30 million. At factory scale, baked transforms
   produce data rates exceeding 57 GB/s, visibility toggling creates
   combinatorial prim explosion, and point instancers sacrifice the
   per-instance addressability that physics and clash detection require.
   The [Manufacturing and logistics](#manufacturing-and-logistics) use
   case below quantifies these costs.

2. **DES-to-USD interchange is broken.** Discrete event simulation
   systems have solved dynamic ownership internally for decades (see
   [Prior art](#prior-art)). When they export to USD, the dynamic
   relationships are lost -- ownership must be flattened into baked
   transforms or point instancers. The USD stage does not contain the
   ownership model.

3. **Cross-domain convergence.** The same structural problem appears
   across industries (see [Industry use cases](#industry-use-cases)).
   Each domain has invented workarounds independently. A standardized
   mechanism would serve all of them.

## Existing mechanisms in USD

Several existing mechanisms partially address aspects of dynamic ownership.
Understanding their capabilities and limitations is essential for scoping
the solution space.

### Prim hierarchy and transform inheritance

Prim hierarchy is USD's sole mechanism for spatial parenting. A child prim
inherits its parent's transform and can have a local offset. This is the
mechanism that needs to be either extended or complemented by a new one.

### UsdGeomPointInstancer

Point instancers represent many objects as elements of a vectorized array
with shared prototypes. Per-instance position, orientation, scale, and
velocity are stored as parallel arrays. Point instancers are the most
scalable representation for large numbers of similar objects.

Limitations for dynamic ownership: instances are not individually
addressable through standard USD queries; they cannot carry per-instance
relationships, overrides, or metadata. Point instancers can participate in
particle-style rigid body simulation (prototype collision shapes, batch
position/velocity updates), but do not support per-instance joints,
per-instance contact queries, or constraint-based attachment. Point instancers
express *where* objects are but not *why* they are there or *what owns them.*

### Relationships and constraints

USD relationships (`UsdRelationship`) can reference other prims, but in standard
USD they do not affect the transform evaluation pipeline. An object cannot
"follow" a referenced prim through transform inheritance -- it can only follow
its hierarchical parent.

Physics constraints (joints) provide runtime spatial coupling between
prims, but joint creation is a runtime operation, not a declarative scene
description feature. Existing implementations (e.g., Isaac Sim's Surface
Gripper) use D6 joints with configurable force limits for grasp/release,
but the mechanism is designed for robotic manipulation scenarios, not for
thousands of simultaneous attachments at factory scale.

### Namespace editing and relocates

`UsdNamespaceEditor` and relocates can reparent prims, but these are authoring-layer
operations -- not animatable or runtime-triggerable. They change the namespace
structure of a stage as a deliberate editorial action, not as a function of time.

## Industry use cases

### Manufacturing and logistics

Manufacturing workflows impose the strictest requirements on dynamic
ownership at scale:

- An automotive assembly plant with 300--500 stations assembles 500 cars
  simultaneously. Each car is built from ~60,000 parts. Parts transfer
  between suppliers, warehouses, AGVs, conveyors, robots, and assembly
  stations. The simulation must represent all 30 million parts and their
  changing carriers.
- A bottling line moves bottles through filling, capping, labeling, and
  packing stations. Visibility toggling handles stacking variation but
  does not represent persistent objects. Baked transforms inflate file
  size 10x (60 MB parented to 600 MB flattened).
- Production deployments use point instancers at the movable-unit level
  for DES exports, with value-clip composability (static geometry and
  animation independently authored). Per-instance joints, contact queries,
  and constraint-based attachment are not supported.

### Media and Entertainment

Film and game production encounters the same structural problem at
smaller object counts but with higher requirements for visual fidelity
and artistic control:

- Character-prop interaction: a character picks up a sword, sheathes it,
  draws it again, throws it. Each transition is a change in spatial
  ownership -- from environment to hand to sheath to hand to physics.
- Destruction sequences: a building collapses, generating thousands of
  fragments that transition from static hierarchy to physics simulation.
  Each fragment must be individually addressable for art-directed
  control.
- Crowd simulations: thousands of agents picking up and dropping props,
  boarding and exiting vehicles.

DCC tools (Maya, Houdini, MotionBuilder) handle these through constraint
systems and runtime parenting APIs that do not serialize into USD. When
shots are published to USD for downstream consumption, the dynamic
relationships are baked out.

### Robotics and simulation

Robotics imposes the strictest requirements on physical correctness
during ownership transitions:

- Grasp-release cycles require continuous transform at the handoff point.
  A part attached to a gripper must transition to physics simulation
  without a discontinuity in position or velocity.
- Multi-robot handoffs (robot A passes a part to robot B) require the
  ownership state to be queryable and the transition to be serializable
  for replay.
- Sensor simulation depends on correct spatial relationships. A part
  "owned by" a gripper must be visible to the gripper's wrist camera at
  the correct relative position.

## Prior art

Two bodies of prior art offer distinct architectural models for
expressing relationships that scene graphs handle through hierarchy.
The DES pattern of a mutable ownership pointer has a concrete
architectural parallel in OpenExec's relationship-driven computation
model (see [Relationship to other proposals](#relationship-to-other-proposals)).
IFC's explicit relationship entities offer a complementary perspective
on separating spatial semantics from hierarchy.

### Discrete event simulation

Every major DES platform separates two concerns that scene graphs
conflate:

1. **Logical ownership** -- a mutable data structure that tracks which
   station, carrier, or container currently "has" each object. This is a
   pointer or reference that changes freely at every handoff event.
2. **Spatial representation** -- the 3D position and visual state of each
   object, derived from the logical ownership at render time.

The logical model is the source of truth. The 3D view is a projection of
it. Objects do not need to be "reparented" in a scene graph -- they
simply update their ownership pointer, and the rendering layer reads the
new parent's transform.

This is precisely what scene-graph-based systems lack. In USD, hierarchy
*is* the ownership model, and there is no separate logical layer that can
change independently of it.

When DES systems export to USD (via Omniverse Connectors or direct USD
writing), the dynamic relationships are lost. A flow item that visits 20
stations would need to be reparented 20 times. USD hierarchy is static,
so the export must flatten to baked transforms or point instancers -- the
semantic ownership information is discarded.

The DES precedent demonstrates that dynamic ownership is solvable at
industrial scale. The question is not *whether* it can work, but how to
express it within a declarative scene description.

### Entity-relationship models (IFC)

The Industry Foundation Classes (IFC) standard takes a fundamentally
different approach to spatial relationships than hierarchical scene
graphs. Where USD expresses "this object belongs to this space" through
parent-child hierarchy, IFC expresses it through explicit relationship
entities:

- `IfcRelContainedInSpatialStructure` declares that a set of elements is
  contained within a spatial element (e.g., furniture in a room).
- `IfcRelAggregates` declares that a whole is decomposed into parts
  (e.g., a building into stories, a story into spaces).
- `IfcRelConnectsElements` declares that two elements are physically
  connected (e.g., a wall to a slab).

These relationships are first-class objects in the data model, not
implicit consequences of namespace position. They can be queried,
filtered, and -- critically -- they can change independently of the
spatial hierarchy. An HVAC unit can be "contained in" Room 101 without
being a child of Room 101 in any namespace sense.

IFC's relationship model does not directly address the time-varying
parenting problem (IFC relationships are not typically time-sampled), but
it offers an important architectural insight: spatial containment and
semantic ownership do not have to be encoded as hierarchy. The tension
between IFC's entity-relationship model and USD's hierarchy-based model
for spatial containment, system membership, and component aggregation is
directly relevant to the AOUSD AECO Interest Group's scope.

The parallels are worth examining: if USD needs a mechanism to express
"this part is currently owned by this carrier," it may be closer to IFC's
explicit relationship model than to a modification of USD's transform
hierarchy.

## Design considerations

This section outlines principles and open questions to guide the community
toward a solution. The goal is to establish consensus on the problem structure
and design principles before committing to a specific mechanism.

### Principles

1. **Separation of concerns.** Animation, parenting, and simulation are
   distinct modes of spatial ownership. Solutions should support each
   mode and their transitions, rather than collapsing them into a single
   mechanism.

2. **Preserve scene graph invariants.** Stable namespace paths enable
   caching, composition, deterministic playback, and non-destructive
   overrides. Any mechanism for dynamic ownership must either preserve
   these properties or make the tradeoff explicit and opt-in.

3. **Scale before elegance.** The problem is qualitatively different at
   10 objects vs. 30 million. A mechanism that works at small scale but
   creates combinatorial explosion at factory scale is not a solution --
   it is a demonstration.

4. **Identity and addressability.** Each transported object should remain
   individually addressable, queryable, and overridable throughout its
   lifecycle. Solutions that sacrifice identity for scale (point
   instancers, particle systems) are useful for visualization but do not
   cover physics, clash detection, or simulation replay.

5. **Interoperability over performance.** A solution that exists only in
   one runtime and cannot be serialized or exchanged solves the problem
   for one tool. A solution that can be expressed in the scene
   description solves it for the ecosystem. The tradeoff between runtime
   performance and interchange capability is the core design tension.

6. **Evidence before standardization.** The community should not
   standardize a mechanism for dynamic ownership without prototype
   evidence demonstrating that it works at representative scale. Both
   candidate approaches (scene-description-level and runtime-level)
   should be implemented and measured before committing to one.

### Open questions and tradeoffs

1. **Which industries are affected, and how important is this to each?**
   Dynamic ownership is the dominant mode of operation in factory and
   logistics simulation, but it also appears in film (character-prop
   interaction), games (destruction, crowds, inventory), robotics
   (grasp-release), and construction (material logistics). The community
   needs to assess relative importance across these domains. If the
   problem is critical to multiple AOUSD constituencies, it warrants
   ecosystem-level investment. If it is primarily an industrial
   simulation concern, the solution space is different. The IEDT and AECO
   Interest Groups, the Physics Working Group, and M&E practitioners each
   bring distinct requirements.

2. **What do the arriving industries' data models tell us?** DES systems
   decouple logical ownership from spatial hierarchy. IFC expresses
   spatial containment through explicit relationship entities. Game
   engine ECS architectures treat parent-child relationships as mutable
   runtime state. These industries designed their data models this way
   because they had to -- dynamic relationships are fundamental to their
   workflows. As their content enters USD, the question is which aspects
   of these models can be expressed within USD's composition and caching
   guarantees, and which cannot. The AECO Interest Group is a natural
   forum for this analysis.

3. **What are the architectural options, and what does each trade away?**
   Seven approaches span the spectrum from pure runtime to full scene
   description:

   - **Baked world-space transforms.** Production-proven. Covers
     animation and parenting (by baking). Does not cover simulation.
     Data volume scales linearly with the product of objects and time
     samples. Loses parent-child semantics.
   - **Point instancers.** Most scalable existing representation. Supports
     particle-style rigid body simulation but not per-instance joints,
     contact queries, or addressability.
   - **Visibility toggling.** Preserves hierarchy at each carrier but
     creates combinatorial prim explosion. Does not represent a single
     persistent object.
   - **Physics joints.** Semantically correct, supports dynamic
     switching. Prim count scales with the product of objects and
     potential carriers.
   - **Time-varying parent relationships.** Would solve the core problem
     directly. Requires changes to scene graph evaluation, caching, and
     serialization. Multi-year standardization effort.
   - **Constraint-based attachment.** Non-hierarchical spatial
     constraints that participate in transform evaluation and can be
     time-varying. Could be implemented as an extension schema.
   - **Computation-driven attachment (OpenExec).** Define a schema with
     a "currentCarrier" relationship; register an OpenExec computation
     that resolves the object's effective transform from the carrier's
     transform plus a local offset. Objects stay in a fixed namespace
     position; their computed transforms follow their carriers. Requires
     a time-varying mechanism for the ownership pointer (USD
     relationships are not time-sampled) and an event-to-authoring
     bridge for simulation handoffs. Uses infrastructure that ships
     with OpenUSD today.

4. **What level of per-instance identity do vectorized representations
   need?** Point instancers are the most scalable existing
   representation, but they do not support per-instance selection,
   override, or constraint-based attachment. Extending them with
   per-instance identity would cover a significant portion of the problem
   space. The tradeoff: richer per-instance data erodes the performance
   advantages that make vectorized representations attractive. It is also
   worth noting that point instancers already support particle-style rigid
   body simulation -- whether that level of physics is sufficient for
   certain dynamic ownership use cases (e.g., parts riding conveyors
   where collision response is needed but joint attachment is not) is
   itself an open question.

5. **How should objects transition between ownership modes?** The handoff
   between animation, parenting, and simulation is where most practical
   problems occur. The transform must be continuous at the handoff point.
   The ownership state must be queryable. The handoff must be
   serializable and replayable. If you have implemented mode transitions
   in production -- whether in industrial simulation, rigging pipelines,
   or destruction and crowd systems -- what worked and what didn't?

### Tradeoff summary

| Approach              | Hierarchy | Scale  | Identity | Physics | Interop   |
| --------------------- | --------- | ------ | -------- | ------- | --------- |
| Baked world-space     | No        | Medium | Yes      | No      | High      |
| Point instancers      | No        | High   | No       | Partial | Medium    |
| Visibility toggling   | Yes       | Low    | No       | Yes     | High      |
| Physics joints        | Yes       | Low    | Yes      | Yes     | High      |
| Time-varying parents  | Yes       | High   | Yes      | Yes     | Low (new) |
| Constraint attachment | Partial   | Medium | Yes      | Partial | Low (new) |
| Computation-driven   | Partial   | High   | Yes      | Partial | Medium    |

No existing approach scores "Yes" across all columns. The approaches
that do require infrastructure that does not yet exist in any major scene
description standard.

### Risks

1. **Scope creep into runtime architecture.** Dynamic ownership touches
   physics engines, constraint solvers, and runtime data layers. The
   proposal should scope to what the scene description needs to express,
   not how runtimes should implement it. Runtimes are free to optimize;
   the scene description defines what is interchangeable.

2. **Premature standardization.** Standardizing a mechanism for
   time-varying hierarchy without prototype evidence risks discovering
   too late that it breaks caching, composition, or deterministic
   playback assumptions. Both candidate approaches should be prototyped
   and measured first.

3. **Ecosystem fragmentation.** If no standard emerges, each runtime and
   pipeline will continue to invent its own workaround. The workarounds
   are individually clever and collectively redundant -- each team
   solving the same problem in isolation.

4. **Backward compatibility.** Any change to how hierarchy works must not
   break existing content or tools. Tools that do not understand dynamic
   ownership should still be able to read the static structure of a stage
   that contains it. Graceful degradation is essential.

5. **The "too hard for USD" dismissal.** There is a risk that the
   community concludes dynamic ownership is fundamentally incompatible
   with declarative scene descriptions and defers the problem
   indefinitely. The DES prior art demonstrates that the concept is
   well-understood and implementable. The question is not whether it can
   be done, but where in the architecture it should live.

## Relationship to other proposals

This proposal connects to several related efforts in the OpenUSD
ecosystem:

- **[Units and Scale in Composed Scenes](../units_and_scale/README.md)**
  -- Addresses a parallel problem: reconciling unit differences when
  heterogeneous content is composed. Both proposals share the theme of
  structural gaps in composition that require ecosystem agreement before
  implementation. Dynamic ownership and unit handling interact in
  practice: when an object changes carriers, the carrier's unit context
  may differ from the object's authored units.

- **[Separation of Concerns for Identifiers](../identifier_separation_of_concerns/README.md)**
  -- Source identifiers that survive namespace edits and reparenting are
  directly relevant to dynamic ownership. If an object changes parents
  over time, its namespace path changes -- but its source identity
  should not.

- **[OpenExec](../openexec/README.md)** -- OpenExec's computation
  framework (shipping with OpenUSD since v25.08) is directly relevant,
  not as a long-horizon dependency but as existing infrastructure.
  OpenExec's `Relationship()` object accessor can follow a USD
  relationship to source a computation from another prim. If a
  "currentCarrier" relationship existed on a transported object, an
  OpenExec computation could resolve the object's effective transform
  from the carrier's transform plus a local offset -- without hierarchy.
  This is architecturally the DES "mutable ownership pointer" pattern
  expressed as a USD computation, with automatic caching and
  invalidation. However, OpenExec cannot modify stage topology
  (no reparenting), USD relationships are not time-sampled (the
  ownership pointer cannot vary with time without authoring changes),
  and the framework is value-driven, not event-driven (simulation
  handoffs require an explicit authoring step). These limitations
  define what the scene description layer still needs to provide:
  a time-varying mechanism for the ownership pointer and an
  event-to-authoring bridge for simulation-driven handoffs.

- **[PointInstancer Object Model](../pointinstancer-object-model/README.md)**
  -- Proposals to extend point instancer capabilities (per-instance
  identity, addressability, overrides) are directly relevant to the
  scale dimension of the dynamic ownership problem.

## Next steps

1. **Submit as pull request.** Submit this proposal to the
   [OpenUSD-proposals](https://github.com/PixarAnimationStudios/OpenUSD-proposals)
   repository. Community feedback on the open questions is welcome there.

2. **Determine cross-industry relevance.** The problem appears in
   manufacturing, film, games, robotics, and construction. Each domain
   has different scale requirements, different tolerance for runtime-only
   solutions, and different expectations for interchange. The IEDT and
   AECO Interest Groups, the Physics Working Group, and M&E practitioners
   should assess relative importance and bring concrete use cases.

3. **Understand what arrives with the content.** The industries adopting
   USD -- manufacturing, AECO, logistics, robotics -- built their data
   models around dynamic relationships because they had to. DES systems,
   IFC, and game engine architectures each represent dynamic ownership
   differently. As their content enters USD, understanding what these
   models express and what USD's design guarantees can accommodate is
   prerequisite analysis. The AECO Interest Group is a natural starting
   point for this work.

4. **Prototype and measure.** Where competing approaches exist
   (scene-description-level vs. runtime-level, time-varying hierarchy vs.
   constraint-based attachment), both should be implemented on
   representative workloads and measured before committing. Performance
   data resolves debates that opinions cannot.

5. **Document workarounds.** Every production team that has shipped a
   digital twin with dynamic ownership has invented a workaround. A
   shared catalog of what was tried, at what scale, and what broke is
   directly useful to anyone designing infrastructure.

Stakeholders who want to accelerate this work are encouraged to engage
directly on any of the steps above. The pace is determined by the breadth
of consensus achieved at each step -- and that consensus is what ensures
the solution serves the full community rather than a single use case.

---

Every production team that has shipped a factory digital twin has
invented a workaround for dynamic ownership. Those workarounds are
individually clever and collectively redundant -- each team solving the
same problem in isolation, making the same tradeoffs, hitting the same
walls at scale. The path forward is to pool that experience: document
what was tried, measure what worked, and bring the evidence to the forums
where infrastructure is being designed. That means you.

## Appendix A: AI-Assisted Drafting

This proposal was drafted with the assistance of an AI language model
(Claude, Anthropic) operating within Cursor IDE, under the direction of
Jens Jebens and Aaron Luk. All conceptual framing, editorial decisions,
and technical judgment are the responsibility of the human authors. The
AI was used as a drafting tool to accelerate the writing process based on
context and direction provided by the authors.

The context provided to the AI was itself the product of extensive
preceding work: stakeholder conversations about factory-scale simulation
workflows, review of discrete event simulation systems and IFC standards,
research into the OpenUSD codebase and OpenExec framework, and iterative
problem space analysis developed over multiple sessions with human review
at every step. The AI did not participate in those conversations; it
received their outputs as input for drafting.

### Context provided to the AI

The following materials were gathered by the authors and provided as
input context. Each item represents human-directed research or
stakeholder engagement that preceded the drafting process:

1. **Stakeholder sync transcript** -- A recorded meeting between domain
   experts covering factory-scale object handling pain points, point
   instancer limitations, physics switching requirements, and DES-to-USD
   export gaps.

2. **Jira user stories** -- Three user stories (POC, EA, GA) tracking
   the object handling work from discovery through factory-scale
   deployment. These defined the scope and acceptance criteria that the
   proposal addresses.

3. **Technology-agnostic problem space analysis** -- A separate document
   analyzing dynamic spatial ownership across any system that uses a
   hierarchical scene graph, covering the three ownership modes, scale
   challenges, workaround tradeoffs, and open questions for the
   community. Developed over two multi-prompt sessions with human review
   and correction at each step, followed by a clarity pass from
   Aaron Luk that broadened the cross-domain framing to include film,
   games, and destruction/crowd use cases alongside manufacturing.

4. **USD/Omniverse-specific analysis** -- A companion document covering
   USD mechanisms (hierarchy, point instancers, namespace editing,
   physics constraints), Omniverse tooling (VFI Guide, Surface Gripper,
   Conveyor Extension, Fabric, Warp), and an 8-step straw-man roadmap
   designed to be validated by the POC.

5. **DES system documentation** -- Plant Simulation, FlexSim, AnyLogic,
   Visual Components, Arena, Simio, ExtendSim. Reviewed for the
   decoupled-ownership architectural pattern and the DES-to-USD export
   gap.

6. **IFC standards research** -- Review of IFC's entity-relationship
   model (`IfcRelContainedInSpatialStructure`, `IfcRelAggregates`,
   `IfcRelConnectsElements`) to understand how spatial containment and
   aggregation are expressed without hierarchy.

7. **OpenExec documentation and API reference** -- Research into
   OpenExec's computation framework (shipping with OpenUSD v25.08),
   including the `Relationship()` object accessor and its architectural
   parallel to the DES mutable-ownership-pointer pattern.

8. **Isaac Sim extension documentation** -- Review of the Surface
   Gripper extension (D6 joints, force limits, batch operations) and
   Conveyor extension to understand existing runtime attachment
   mechanisms and their scale limitations.

9. **Existing proposals in this repository** -- The
   [Separation of Concerns for Identifiers](../identifier_separation_of_concerns/README.md)
   and [Units and Scale](../units_and_scale/README.md) proposals were
   used as structural and formatting references.

10. **Field observations** -- Internal observations from virtual factory
    deployments including workaround costs, data volume measurements,
    and point instancer limitations.

### Review and refinement

The draft was refined through multiple rounds of review. Key editorial
decisions included:

- Compressing the introduction from the problem space document's
  55-line version to 3 paragraphs, relocating the factory walkthrough
  into "Why Scene Graphs Cannot Express Dynamic Ownership" as concrete
  motivation.
- Adding the co-dependency framing: the ecosystem must determine whether
  dynamic ownership should be expressed in the scene description or the
  runtime, but cannot make that decision without prototype evidence.
  Iteratively refined from a prescriptive "the ecosystem must decide"
  to an exploratory framing grounded in the observation that the
  industries adopting USD already built their data models around
  dynamic relationships.
- Adding IFC entity-relationship models as prior art alongside DES,
  after identifying that IFC's explicit relationship objects
  (containment, aggregation, connection) offer a complementary
  architectural insight to DES's mutable-pointer pattern.
- Expanding the OpenExec reference from a 4-line placeholder to a
  substantive analysis, including the `Relationship()` accessor as a
  DES mutable-pointer analogue, and adding computation-driven
  attachment as a seventh architectural approach in the tradeoff
  analysis.
- Correcting the claim that point instancers "cannot participate in
  physics" -- PhysX supports collision on point instancer prototypes.
  Replaced with accurate framing: PIs support particle-style rigid body
  simulation but not per-instance joints, contact queries, or
  constraint-based attachment. Added this as an open question: whether
  PI-level physics is sufficient for certain dynamic ownership use
  cases is itself worth examining.
- Reframing the Film and game production bullet to acknowledge that
  DCC constraint rigs baked into USD are a working workflow at shot
  scale, rather than implying M&E doesn't have a solution.
- Updating the Isaac Sim Surface Gripper description from "fixed joints,
  CPU-only" to "D6 joints with configurable force limits" per current
  documentation.
- Removing partner and customer names from the document.

A prompt-level drafting log for the problem space documents has been
archived separately.
