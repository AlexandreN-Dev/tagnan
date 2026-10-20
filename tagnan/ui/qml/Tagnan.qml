// Tagnan: flat Prussian-blue ink (tagnan/art.py), alive. The pose comes from the animator
// (tagnan/ui/animator.py), 30 times a second. Children work in the drawing's coordinates
// (120 x 140, feet at (60, 132)); the ink and the SVG layers are rendered at the screen's own
// resolution, so nothing blurs when the figure is scaled up.
import QtQuick
import QtQuick.Shapes

Item {
    id: root

    required property QtObject animator
    required property var spec  // tagnan.art.figure(grade)
    // A promotion under way (controller.promotion): {"from": grade, "to": grade}, else empty.
    property var promotion: ({})

    readonly property int stage: spec.stage
    readonly property string expression: animator.expression
    readonly property real unit: Math.min(width / 120, height / 140)
    // Device pixels per unit of the drawing, at this grade's scale.
    readonly property real px: unit * Screen.devicePixelRatio * spec.scale
    readonly property real guard: animator.guard
    // The rapier floats beside him, as Dartt's: from its rest (point down) to en garde.
    readonly property var rapierAt: spec.hasRapier
        ? [spec.rapierDown[0] + (spec.rapierUp[0] - spec.rapierDown[0]) * guard,
           spec.rapierDown[1] + (spec.rapierUp[1] - spec.rapierDown[1]) * guard,
           spec.rapierDown[2] + (spec.rapierUp[2] - spec.rapierDown[2]) * guard]
        : [0, 0, 0]
    // The drip grows, lets go and falls, once every few seconds.
    readonly property real dripScale: {
        const v = animator.drip
        return v < 0.55 ? 0.15 + 0.85 * v / 0.55 : v < 0.6 ? 1 - 0.85 * (v - 0.55) / 0.05 : 0.15
    }
    readonly property real fallT: animator.drip < 0.57 || animator.drip > 0.76 ? -1 : (animator.drip - 0.57) / 0.19
    // The Cadet's drip lands on his puddle (spec.landing, the desk's y) and rings it.
    readonly property bool lands: spec.landing >= 0
    readonly property real splashT: animator.drip < 0.76 || animator.drip > 0.96 ? -1 : (animator.drip - 0.76) / 0.2
    // The Cadet's hat rides his rippling head (tagnan.art.hat_ride) on top of its own sway.
    readonly property real hatAngle: animator.hat + animator.hatRideTip

    // His evolution, as in the games: he turns white, his old and new looks swap faster and
    // faster, a flash, and he stands in his new one. The controller changes his grade while he
    // is white and shows it at the flash (PROMOTION_SWAP_MS, PROMOTION_REVEAL_MS).
    property int evolveFrom: 0
    property int evolveTo: 0
    property real cover: 0  // the white silhouette over him
    property real swing: 0  // 0 to 1, faster and faster: which look the silhouette has
    property real rays: 0
    property real flash: 0
    readonly property bool covered: cover >= 1
    readonly property bool showsNew: Math.floor(swing * 15) % 2 === 1
    readonly property point heart: Qt.point(60, 80)  // where the rays meet, the flash bursts

    onPromotionChanged: {
        if (promotion.to === undefined)
            return
        evolveFrom = promotion.from
        evolveTo = promotion.to
        evolution.restart()
    }

    SequentialAnimation {
        id: evolution
        ScriptAction {
            script: {
                root.cover = 0
                root.swing = 0
                root.rays = 0
                root.flash = 0
            }
        }
        PauseAnimation { duration: 700 }  // he cheers the right answer first
        ParallelAnimation {
            NumberAnimation { target: root; property: "cover"; to: 1; duration: 400; easing.type: Easing.InOutQuad }
            NumberAnimation { target: root; property: "rays"; to: 1; duration: 400 }
        }
        NumberAnimation { target: root; property: "swing"; to: 1; duration: 2600; easing.type: Easing.InQuad }
        NumberAnimation { target: root; property: "flash"; to: 1; duration: 150 }
        ScriptAction {
            script: {
                root.cover = 0
                root.rays = 0
            }
        }
        NumberAnimation { target: root; property: "flash"; to: 0; duration: 650; easing.type: Easing.OutQuad }
    }

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
    // Where a drip hangs from: the Gascon's follow his rippling edge (tagnan.art.drip_tops).
    function dripTop(i, fallback) {
        const tops = root.animator.dripTops
        return tops && i < tops.length ? tops[i] : fallback
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
                PathSvg { path: root.ellipse(60, 133.5, root.spec.shadowRx, 3.6) }
            }
        }

        Item {
            id: staged
            width: 120
            height: 140
            opacity: root.covered ? 0 : 1
            transform: Scale { origin.x: 60; origin.y: 132; xScale: root.spec.scale; yScale: root.spec.scale }

            // What lies on the desk never moves: the cap, a blot, the knocked-over inkwell, the
            // split one.
            Layer { name: "ground"; visible: root.stage <= 2 }
            // Where the Cadet's drip lands, a ring widens on his puddle.
            Shape {
                anchors.fill: parent
                visible: root.lands && root.splashT >= 0
                opacity: 0.9 * (1 - Math.max(0, root.splashT))
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    fillColor: "transparent"
                    strokeColor: root.spec.inkEdge
                    strokeWidth: 0.8
                    PathSvg {
                        readonly property real r: 1.2 + 6 * Math.max(0, root.splashT)
                        path: root.lands ? root.ellipse(root.spec.drip[0], root.spec.landing - 0.2, r, r * 0.28) : ""
                    }
                }
            }

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

                // Dartt's glow: a blurred silhouette that breathes in and out.
                Layer { name: "glow"; opacity: Math.min(1, root.animator.glow * 1.25) }

                // Droplets floating around him; the Gascon's have their shade and point of light
                // (tagnan.art.drop_shade, drop_light).
                Repeater {
                    model: root.spec.drops
                    Shape {
                        id: drop
                        required property var modelData
                        required property int index
                        readonly property bool finished: root.spec.dropShades.length > index
                        readonly property var light: finished ? root.spec.dropLights[index] : [0, 0, 0]
                        anchors.fill: parent
                        preferredRendererType: Shape.CurveRenderer
                        transform: Translate {
                            x: root.animator.drops[2 * index] || 0
                            y: root.animator.drops[2 * index + 1] || 0
                        }
                        ShapePath {
                            fillColor: root.spec.ink
                            strokeColor: "transparent"
                            PathSvg { path: root.ellipse(drop.modelData[0], drop.modelData[1], drop.modelData[2], drop.modelData[2]) }
                        }
                        ShapePath {
                            fillColor: root.spec.shade
                            strokeColor: "transparent"
                            PathSvg { path: drop.finished ? root.spec.dropShades[drop.index] : "" }
                        }
                        ShapePath {
                            fillColor: root.spec.dropLight
                            strokeColor: "transparent"
                            PathSvg { path: drop.light[2] > 0 ? root.ellipse(drop.light[0], drop.light[1], drop.light[2], drop.light[2]) : "" }
                        }
                    }
                }

                // The Cadet's ribbon tails, behind his head: they ride with his hat and swing.
                Layer {
                    name: "tails"
                    visible: root.spec.tails.length > 0
                    transform: [
                        Rotation {
                            origin.x: root.spec.tails.length ? root.spec.tails[0] : 0
                            origin.y: root.spec.tails.length ? root.spec.tails[1] : 0
                            angle: 0.7 * root.animator.plume
                        },
                        Rotation {
                            origin.x: root.spec.hasHat ? root.spec.hat[0] : 0
                            origin.y: root.spec.hasHat ? root.spec.hat[1] : 0
                            angle: root.hatAngle
                        },
                        Translate { y: root.animator.hatRideY }
                    ]
                }

                // The Cadet's ink stays under his brim, wherever his hat sits, so that it never
                // shows through the felt: clipped in the hat's frame (spec.underHat), then brought
                // back to the body's.
                Item {
                    id: underBrim
                    readonly property bool under: root.spec.underHat >= 0
                    width: 120
                    height: 140
                    transform: [
                        Rotation {
                            origin.x: root.spec.hasHat ? root.spec.hat[0] : 0
                            origin.y: root.spec.hasHat ? root.spec.hat[1] : 0
                            angle: underBrim.under ? root.hatAngle : 0
                        },
                        Translate { y: underBrim.under ? root.animator.hatRideY : 0 }
                    ]
                    Item {
                        x: -200
                        y: underBrim.under ? root.spec.underHat : -200
                        width: 520
                        height: 540
                        clip: underBrim.under
                        Item {
                            id: ink
                            x: 200
                            y: -parent.y
                            width: 120
                            height: 140
                            transform: [
                                Translate { y: underBrim.under ? -root.animator.hatRideY : 0 },
                                Rotation {
                                    origin.x: root.spec.hasHat ? root.spec.hat[0] : 0
                                    origin.y: root.spec.hasHat ? root.spec.hat[1] : 0
                                    angle: underBrim.under ? -root.hatAngle : 0
                                }
                            ]

                            Ink {
                                visible: root.spec.shadeOffset[0] !== 0 || root.spec.shadeOffset[1] !== 0
                                d: root.animator.inkPath
                                fill: root.spec.shade
                                transform: Translate { x: root.spec.shadeOffset[0]; y: root.spec.shadeOffset[1] }
                            }
                            Ink { d: root.animator.inkPath }
                            // Grade 0: the inkwell's ink, shaded on the right, lit under its surface, with
                            // its meniscus; all three follow the slosh (tagnan.art.inkwell_shading).
                            // Grade 1: the Gascon's, shaded on the lower right, lit on the upper left, with
                            // a rim of light; all three follow the ripple (tagnan.art.splash_shading).
                            Shape {
                                visible: root.stage <= 2
                                anchors.fill: parent
                                preferredRendererType: Shape.CurveRenderer
                                ShapePath {
                                    fillColor: root.spec.shade
                                    strokeColor: "transparent"
                                    PathSvg { path: root.animator.inkShade }
                                }
                                ShapePath {
                                    fillColor: root.spec.inkLight
                                    strokeColor: "transparent"
                                    PathSvg { path: root.animator.inkLight }
                                }
                                ShapePath {
                                    fillColor: root.stage >= 1 ? root.spec.inkEdge : "transparent"
                                    strokeColor: root.stage === 0 ? root.spec.inkEdge : "transparent"
                                    strokeWidth: root.spec.meniscusWidth
                                    capStyle: ShapePath.RoundCap
                                    PathSvg { path: root.animator.inkEdge }
                                }
                            }
                            // The drips; the Gascon's and the Cadet's hang under their ink, from its
                            // rippling edge.
                            Repeater {
                                model: root.spec.staticDrips
                                Ink {
                                    required property var modelData
                                    required property int index
                                    z: root.spec.dripsUnder ? -1 : 0
                                    d: root.teardrop(modelData[0], root.dripTop(index, modelData[1]), modelData[2])
                                }
                            }
                            Ink {
                                id: drip
                                readonly property real hangs: root.spec.drip.length
                                    ? root.dripTop(root.spec.staticDrips.length, root.spec.drip[1]) : 0
                                visible: root.spec.drip.length > 0
                                z: root.spec.dripsUnder ? -1 : 0
                                d: visible ? root.teardrop(root.spec.drip[0], hangs, root.spec.drip[2]) : ""
                                transform: Scale {
                                    origin.x: root.spec.drip.length ? root.spec.drip[0] : 0
                                    origin.y: drip.hangs
                                    yScale: root.dripScale
                                }
                            }
                            // The drop that lets go: it fades as it falls, or the Cadet's lands on his
                            // puddle, below him for all his lift.
                            Ink {
                                id: fall
                                readonly property real from: drip.hangs + (root.spec.fall.length ? root.spec.fall[1] - root.spec.drip[1] : 0)
                                visible: root.spec.fall.length > 0 && root.fallT >= 0
                                opacity: root.lands ? 1 : 1 - Math.max(0, root.fallT)
                                d: root.spec.fall.length
                                    ? root.ellipse(root.spec.fall[0], from, root.spec.fall[2], root.spec.fall[2])
                                    : ""
                                transform: Translate {
                                    y: (root.lands ? root.spec.landing - 1.6 + root.spec.lift - fall.from : 16)
                                        * Math.pow(Math.max(0, root.fallT), 2)
                                }
                            }
                        }
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
                    transform: Rotation {
                        origin.x: root.stage === 0 ? root.spec.quill[0] : 0
                        origin.y: root.stage === 0 ? root.spec.quill[1] : 0
                        angle: root.animator.quill
                    }
                }
                Layer { name: "glass"; visible: root.stage === 0 }

                // The hat, its plumes swaying on top.
                Item {
                    visible: root.spec.hasHat
                    width: 120
                    height: 140
                    transform: [
                        Rotation {
                            origin.x: root.spec.hasHat ? root.spec.hat[0] : 0
                            origin.y: root.spec.hasHat ? root.spec.hat[1] : 0
                            angle: root.hatAngle
                        },
                        Translate { y: root.animator.hatRideY }
                    ]
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

                // The rapier, floating beside him: point down at rest, raised en garde, swaying.
                Item {
                    visible: root.spec.hasRapier
                    x: root.rapierAt[0]
                    y: root.rapierAt[1] + root.animator.swordY
                    transformOrigin: Item.TopLeft
                    rotation: root.rapierAt[2] + root.animator.sword
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


            // What lies on the desk in front of him: the Cadet's quill, out of its inkwell.
            Layer { name: "front"; visible: root.stage === 2 }
            }
        }

        // His evolution: rays drawn in to him, his white silhouette, the flash.
        Repeater {
            model: 12
            Rectangle {
                required property int index
                readonly property real outer: 58 - 30 * root.swing
                readonly property real inner: 30 - 22 * root.swing
                visible: root.rays > 0
                opacity: 0.8 * root.rays
                x: root.heart.x - 0.7
                y: root.heart.y - outer
                width: 1.4
                height: outer - inner
                radius: 0.7
                gradient: Gradient {
                    GradientStop { position: 0; color: "#00C8DCFF" }
                    GradientStop { position: 1; color: "#C8DCFF" }
                }
                transform: Rotation { origin.x: 0.7; origin.y: outer; angle: index * 30 }
            }
        }
        Item {
            width: 120
            height: 140
            visible: root.cover > 0
            opacity: root.cover
            Image {
                width: 120
                height: 140
                source: "image://tagnan/" + (root.showsNew ? root.evolveTo : root.evolveFrom) + "/silhouette/-"
                sourceSize: Qt.size(Math.ceil(120 * root.unit * Screen.devicePixelRatio),
                                    Math.ceil(140 * root.unit * Screen.devicePixelRatio))
                smooth: true
            }
        }
        Shape {
            anchors.fill: parent
            visible: root.flash > 0
            opacity: root.flash
            preferredRendererType: Shape.CurveRenderer
            transform: Scale {
                origin.x: root.heart.x
                origin.y: root.heart.y
                xScale: 0.6 + 0.6 * root.flash
                yScale: 0.6 + 0.6 * root.flash
            }
            ShapePath {
                strokeColor: "transparent"
                fillGradient: RadialGradient {
                    centerX: root.heart.x
                    centerY: root.heart.y
                    centerRadius: 60
                    focalX: root.heart.x
                    focalY: root.heart.y
                    GradientStop { position: 0; color: "#FFFFFFFF" }
                    GradientStop { position: 0.45; color: "#E6FFFFFF" }
                    GradientStop { position: 1; color: "#00FFFFFF" }
                }
                PathSvg { path: root.ellipse(root.heart.x, root.heart.y, 60, 60) }
            }
        }

        // The mood's sign above him: a question mark, sparkles, a vein of anger. It pops in.
        Layer {
            name: "decor"
            byExpression: true
            visible: !root.covered && (root.expression === "ask" || root.expression === "happy" || root.expression === "angry")
            transform: Scale {
                origin.x: root.spec.decor[0]
                origin.y: root.spec.decor[1]
                xScale: Math.max(0, root.animator.decor)
                yScale: Math.max(0, root.animator.decor)
            }
        }
    }
}
