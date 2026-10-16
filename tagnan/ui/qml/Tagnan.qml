// Tagnan: flat Prussian-blue ink (tagnan/art.py), alive. The pose comes from the animator
// (tagnan/ui/animator.py), 30 times a second. Children work in the drawing's coordinates
// (120 x 140, feet at (60, 132)); the ink and the SVG layers are rendered at the screen's own
// resolution, so nothing blurs when the figure is scaled up.
import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: root

    required property QtObject animator
    required property var spec  // tagnan.art.figure(grade)

    readonly property int stage: spec.stage
    readonly property string expression: animator.expression
    readonly property real unit: Math.min(width / 120, height / 140)
    // Device pixels per unit of the drawing, at this grade's scale.
    readonly property real px: unit * Screen.devicePixelRatio * spec.scale
    readonly property real guard: animator.guard
    // The rapier's hand, between the lowered and the raised pose.
    readonly property bool armed: spec.shoulder.length > 0
    readonly property real armAngle: armed ? spec.armDown + (spec.armUp - spec.armDown) * guard : 0
    readonly property real armLength: armed ? spec.armLength + (spec.armLengthUp - spec.armLength) * guard : 0
    readonly property point hand: armed
        ? Qt.point(spec.shoulder[0] + armLength * Math.cos(armAngle * Math.PI / 180),
                   spec.shoulder[1] + armLength * Math.sin(armAngle * Math.PI / 180))
        : Qt.point(0, 0)
    // The drip grows, lets go and falls, once every few seconds.
    readonly property real dripScale: {
        const v = animator.drip
        return v < 0.55 ? 0.15 + 0.85 * v / 0.55 : v < 0.6 ? 1 - 0.85 * (v - 0.55) / 0.05 : 0.15
    }
    readonly property real fallT: animator.drip < 0.57 || animator.drip > 0.76 ? -1 : (animator.drip - 0.57) / 0.19

    implicitWidth: 150
    implicitHeight: 175

    function layerUrl(name, byExpression) {
        return "image://tagnan/" + stage + "/" + name + "/" + (byExpression ? expression : "-")
    }
    function ellipse(cx, cy, rx, ry) {
        return "M" + (cx - rx) + " " + cy + " A" + rx + " " + ry + " 0 1 0 " + (cx + rx) + " " + cy
            + " A" + rx + " " + ry + " 0 1 0 " + (cx - rx) + " " + cy + " Z"
    }
    function segment(s) {
        return "M" + s[0] + " " + s[1] + " L" + s[2] + " " + s[3]
    }
    function teardrop(x, y, r) {
        return "M" + x + " " + y
            + " C" + (x - r * 0.7) + " " + (y + r) + " " + (x - r) + " " + (y + r * 2) + " " + (x - r) + " " + (y + r * 2.6)
            + " A" + r + " " + r + " 0 0 0 " + (x + r) + " " + (y + r * 2.6)
            + " C" + (x + r) + " " + (y + r * 2) + " " + (x + r * 0.7) + " " + (y + r) + " " + x + " " + y + " Z"
    }
    // A tap's droplet: up its arc fast, then down, shrinking and fading (tagnan.art.burst).
    function droplet(d, t) {
        const u = (t - d[7]) / d[8]
        if (t < 0 || u < 0 || u > 1)
            return { x: 0, y: 0, s: 0, o: 0 }
        if (u < 0.55) {
            const e = 1 - Math.pow(1 - u / 0.55, 2)
            return { x: d[2] * e, y: d[3] * e, s: 0.3 + 0.7 * e, o: 1 }
        }
        const v = Math.pow((u - 0.55) / 0.45, 2)
        return { x: d[2] + (d[4] - d[2]) * v, y: d[3] + (d[5] - d[3]) * v, s: 1 - 0.6 * v, o: 1 - v }
    }
    // Between his eyes, on the screen: where the pointer is looked at from.
    function eyesOnScreen() {
        const eyes = root.spec.eyes
        return staged.mapToGlobal((eyes[0][0] + eyes[1][0]) / 2, eyes[0][1] - root.spec.lift)
    }

    // A piece of the drawing: an SVG layer, full frame.
    component Layer: Image {
        property string name
        property bool byExpression: false
        width: 120
        height: 140
        source: root.layerUrl(name, byExpression)
        sourceSize: Qt.size(Math.ceil(120 * root.px), Math.ceil(140 * root.px))
        smooth: true
    }
    // Flat ink, filled.
    component Ink: Shape {
        property string d
        property color fill: root.spec.ink
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: fill
            strokeColor: "transparent"
            PathSvg { path: d }
        }
    }
    // An arm: a round-capped stroke of ink.
    component Bar: Shape {
        property var seg: [0, 0, 0, 0, 1]
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: "transparent"
            strokeColor: root.spec.ink
            strokeWidth: seg[4]
            capStyle: ShapePath.RoundCap
            PathSvg { path: root.segment(seg) }
        }
    }

    Item {
        id: box
        width: 120
        height: 140
        x: (root.width - 120 * root.unit) / 2
        y: root.height - 140 * root.unit
        transform: Scale { xScale: root.unit; yScale: root.unit }

        // His shadow on the desk, smaller while he is in the air.
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            transform: Scale { origin.x: 60; origin.y: 133.5; xScale: root.animator.shadow; yScale: root.animator.shadow }
            ShapePath {
                fillColor: "#29000000"
                strokeColor: "transparent"
                PathSvg { path: root.ellipse(60, 133.5, 28 * root.spec.scale, 3.6) }
            }
        }

        Item {
            id: staged
            width: 120
            height: 140
            transform: Scale { origin.x: 60; origin.y: 132; xScale: root.spec.scale; yScale: root.spec.scale }

            // What lies on the desk never moves: the cap, a blot, the knocked-over inkwell.
            Layer { name: "ground"; visible: root.stage <= 1 }

            // Everything else rides on his body: lift, sulky turn, squash and stretch, hops.
            Item {
                id: reactor
                width: 120
                height: 140
                transform: [
                    Translate { y: -root.spec.lift },
                    Rotation { origin.x: 60; origin.y: 130; angle: root.animator.bodyTurn },
                    Scale { origin.x: 60; origin.y: 130; xScale: root.animator.bodySx; yScale: root.animator.bodySy },
                    Translate { x: root.animator.bodyX; y: root.animator.bodyY }
                ]

                // Droplets floating around him.
                Repeater {
                    model: root.spec.drops
                    Shape {
                        required property var modelData
                        required property int index
                        anchors.fill: parent
                        preferredRendererType: Shape.CurveRenderer
                        transform: Translate {
                            x: root.animator.drops[2 * index] || 0
                            y: root.animator.drops[2 * index + 1] || 0
                        }
                        ShapePath {
                            fillColor: root.spec.ink
                            strokeColor: "transparent"
                            PathSvg { path: root.ellipse(modelData[0], modelData[1], modelData[2], modelData[2]) }
                        }
                    }
                }

                // The ink, its shade, the arms and the drip, with Dartt's glow.
                Item {
                    id: ink
                    width: 120
                    height: 140
                    layer.enabled: true
                    layer.sourceRect: Qt.rect(-24, -24, 168, 188)
                    layer.textureSize: Qt.size(Math.ceil(168 * root.px), Math.ceil(188 * root.px))
                    layer.smooth: true
                    // The software renderer (offscreen previews) has no shaders: ink without its glow.
                    layer.effect: GraphicsInfo.api === GraphicsInfo.Software ? null : glow

                    Component {
                        id: glow
                        MultiEffect {
                            shadowEnabled: true
                            shadowColor: root.spec.glow
                            shadowOpacity: Math.min(1, root.animator.glow * 1.35)
                            blurMax: 64
                            shadowBlur: Math.min(1, 15 * root.px / 64)
                            shadowHorizontalOffset: 0
                            shadowVerticalOffset: 0
                        }
                    }

                    Ink {
                        d: root.animator.inkPath
                        fill: root.spec.shade
                        transform: Translate { x: root.spec.shadeOffset[0]; y: root.spec.shadeOffset[1] }
                    }
                    Ink { d: root.animator.inkPath }
                    Repeater {
                        model: root.spec.arms
                        Bar {
                            required property var modelData
                            seg: modelData
                        }
                    }
                    Bar {
                        visible: root.armed
                        seg: root.armed ? [root.spec.shoulder[0], root.spec.shoulder[1], root.hand.x, root.hand.y, root.spec.armWidth] : [0, 0, 0, 0, 1]
                    }
                    Repeater {
                        model: root.spec.staticDrips
                        Ink {
                            required property var modelData
                            d: root.teardrop(modelData[0], modelData[1], modelData[2])
                        }
                    }
                    Ink {
                        visible: root.spec.drip.length > 0
                        d: visible ? root.teardrop(root.spec.drip[0], root.spec.drip[1], root.spec.drip[2]) : ""
                        transform: Scale {
                            origin.x: root.spec.drip.length ? root.spec.drip[0] : 0
                            origin.y: root.spec.drip.length ? root.spec.drip[1] : 0
                            yScale: root.dripScale
                        }
                    }
                    Ink {
                        visible: root.spec.fall.length > 0 && root.fallT >= 0
                        opacity: 1 - Math.max(0, root.fallT)
                        d: root.spec.fall.length ? root.ellipse(root.spec.fall[0], root.spec.fall[1], root.spec.fall[2], root.spec.fall[2]) : ""
                        transform: Translate { y: 16 * Math.pow(Math.max(0, root.fallT), 2) }
                    }
                }

                // A tap splashes droplets off his edge, and a ring widens in the ink.
                Shape {
                    id: ring
                    readonly property real t: root.animator.burst
                    readonly property real u: Math.min(1, Math.max(0, t / 0.75))
                    anchors.fill: parent
                    visible: t >= 0 && t < 0.75 && root.spec.ring.length > 0
                    opacity: 0.55 * (1 - u)
                    preferredRendererType: Shape.CurveRenderer
                    transform: Scale {
                        origin.x: root.spec.ring.length ? root.spec.ring[0] : 0
                        origin.y: root.spec.ring.length ? root.spec.ring[1] : 0
                        xScale: 0.72 + 0.58 * ring.u
                        yScale: 0.72 + 0.58 * ring.u
                    }
                    ShapePath {
                        fillColor: "transparent"
                        strokeColor: root.spec.ink
                        strokeWidth: 1.6
                        PathSvg {
                            path: root.spec.ring.length ? root.ellipse(root.spec.ring[0], root.spec.ring[1], root.spec.ring[2], root.spec.ring[3]) : ""
                        }
                    }
                }
                Repeater {
                    model: root.spec.burst
                    Shape {
                        required property var modelData
                        readonly property var at: root.droplet(modelData, root.animator.burst)
                        anchors.fill: parent
                        visible: at.o > 0
                        opacity: at.o
                        preferredRendererType: Shape.CurveRenderer
                        transform: [
                            Scale { origin.x: modelData[0]; origin.y: modelData[1]; xScale: at.s; yScale: at.s },
                            Translate { x: at.x; y: at.y }
                        ]
                        ShapePath {
                            fillColor: root.spec.ink
                            strokeColor: "transparent"
                            PathSvg { path: root.ellipse(modelData[0], modelData[1], modelData[6], modelData[6]) }
                        }
                    }
                }

                Layer { name: "cross"; visible: root.stage >= 3 }

                // Eyes: looking moves both; blinking and the idle wink squash each.
                Item {
                    width: 120
                    height: 140
                    transform: Translate { x: root.animator.gazeX; y: root.animator.gazeY }
                    Layer {
                        name: "eye-left"
                        byExpression: true
                        transform: Scale {
                            origin.x: root.spec.eyes[0][0]
                            origin.y: root.spec.eyes[0][1]
                            yScale: Math.max(0.08, root.animator.eyeOpen * (1 - 0.9 * root.animator.wink))
                        }
                    }
                    Layer {
                        name: "eye-right"
                        byExpression: true
                        transform: Scale {
                            origin.x: root.spec.eyes[1][0]
                            origin.y: root.spec.eyes[1][1]
                            yScale: Math.max(0.08, root.animator.eyeOpen)
                        }
                    }
                }
                Layer { name: "mouth"; byExpression: true }
                Layer {
                    name: "moustache"
                    visible: root.spec.hasMoustache
                    transform: Rotation {
                        origin.x: root.spec.hasMoustache ? root.spec.moustache[0] : 0
                        origin.y: root.spec.hasMoustache ? root.spec.moustache[1] : 0
                        angle: root.animator.moustache
                    }
                }
                Layer { name: "royale"; byExpression: true; visible: root.stage >= 5 }

                // Grade 0: the face is in the ink, behind the quill and the glass.
                Layer {
                    name: "quill"
                    visible: root.stage === 0
                    transform: Rotation { origin.x: 61; origin.y: 104; angle: root.animator.quill }
                }
                Layer { name: "glass"; visible: root.stage === 0 }

                // The hat, its plumes swaying on top.
                Item {
                    visible: root.spec.hasHat
                    width: 120
                    height: 140
                    transform: Rotation {
                        origin.x: root.spec.hasHat ? root.spec.hat[0] : 0
                        origin.y: root.spec.hasHat ? root.spec.hat[1] : 0
                        angle: root.animator.hat
                    }
                    Layer {
                        name: "plume"
                        visible: root.spec.hasPlume
                        transform: Rotation {
                            origin.x: root.spec.hasHat ? root.spec.plume[0] : 0
                            origin.y: root.spec.hasHat ? root.spec.plume[1] : 0
                            angle: root.animator.plume
                        }
                    }
                    Layer { name: "hat"; visible: root.spec.hasHat }
                }

                // The rapier, in the hand: down at his side, raised en garde, swinging.
                Item {
                    visible: root.spec.hasRapier
                    x: root.hand.x
                    y: root.hand.y
                    transformOrigin: Item.TopLeft
                    rotation: root.spec.hasRapier
                        ? root.spec.rapierDown + (root.spec.rapierUp - root.spec.rapierDown) * root.guard + root.animator.sword
                        : 0
                    scale: root.spec.hasRapier ? root.spec.rapierScale : 1
                    Image {
                        readonly property var frame: root.spec.hasRapier ? root.spec.rapierBox : [0, 0, 1, 1]
                        readonly property var grip: root.spec.hasRapier ? root.spec.rapierGrip : [0, 0]
                        x: frame[0] - grip[0]
                        y: frame[1] - grip[1]
                        width: frame[2]
                        height: frame[3]
                        source: root.spec.hasRapier ? root.layerUrl("rapier", false) : ""
                        sourceSize: Qt.size(Math.ceil(frame[2] * root.px * parent.scale), Math.ceil(frame[3] * root.px * parent.scale))
                        smooth: true
                    }
                }

            }
        }

        // The mood's sign above him: a question mark, sparkles, a vein of anger. It pops in.
        Layer {
            name: "decor"
            byExpression: true
            visible: root.expression === "ask" || root.expression === "happy" || root.expression === "angry"
            transform: Scale {
                origin.x: root.spec.decor[0]
                origin.y: root.spec.decor[1]
                xScale: Math.max(0, root.animator.decor)
                yScale: Math.max(0, root.animator.decor)
            }
        }
    }
}
