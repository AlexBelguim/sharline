//! Fonts and the type scale of the hub mockups. Barlow (body) and Barlow Condensed (display) are compiled
//! into the binary (SIL OFL, see `game/assets/fonts/OFL.txt`). Letter spacing is CSS em × font size in px;
//! Bevy has no text-transform, so upper-case roles upper-case their copy here.

use super::tokens::*;
use bevy::prelude::*;
use bevy::text::{FontFeatureTag, LetterSpacing, LineHeight};

macro_rules! font_bytes {
    ($name:literal) => {
        include_bytes!(concat!("../../../../assets/fonts/", $name))
    };
}

/// The two families of the mockups.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Face {
    /// Barlow: body copy.
    Body,
    /// Barlow Condensed: titles, labels, numbers, buttons (`--fd`).
    Display,
}

/// One handle per static font file (`TextFont.weight` only affects variable fonts).
#[derive(Resource, Clone)]
pub struct UiFonts {
    /// Barlow 400, 500, 600, 700.
    body: [Handle<Font>; 4],
    body_italic: Handle<Font>,
    /// Barlow Condensed 500, 600, 700.
    display: [Handle<Font>; 3],
}

impl UiFonts {
    pub(super) fn load(fonts: &mut Assets<Font>) -> Self {
        let mut add = |bytes: &[u8]| fonts.add(Font::from_bytes(bytes.to_vec()));
        Self {
            body: [
                add(font_bytes!("Barlow-Regular.ttf")),
                add(font_bytes!("Barlow-Medium.ttf")),
                add(font_bytes!("Barlow-SemiBold.ttf")),
                add(font_bytes!("Barlow-Bold.ttf")),
            ],
            body_italic: add(font_bytes!("Barlow-Italic.ttf")),
            display: [
                add(font_bytes!("BarlowCondensed-Medium.ttf")),
                add(font_bytes!("BarlowCondensed-SemiBold.ttf")),
                add(font_bytes!("BarlowCondensed-Bold.ttf")),
            ],
        }
    }

    /// The file closest to `weight` (400..700) in `face`.
    pub fn handle(&self, face: Face, weight: u16) -> Handle<Font> {
        match face {
            Face::Body => self.body[((weight.clamp(400, 700) - 400) / 100) as usize].clone(),
            Face::Display => self.display[((weight.clamp(500, 700) - 500) / 100) as usize].clone(),
        }
    }

    pub fn font(&self, face: Face, weight: u16, size: f32) -> TextFont {
        TextFont::from_font_size(size).with_font(self.handle(face, weight))
    }

    /// Text in a face, weight, size (px at 1080p), colour and letter spacing (em, like the CSS).
    /// The line box is the browser's `normal` one ([`css_normal_line`]); [`UiFonts::text_line`] takes another.
    /// The bundle already holds a `LineHeight`: do not add a second one next to it (a duplicate panics).
    pub fn text(&self, s: impl Into<String>, face: Face, weight: u16, size: f32, color: Color, em: f32) -> impl Bundle {
        self.text_line(s, face, weight, size, color, em, LineHeight::Px(css_normal_line(size)))
    }

    /// [`UiFonts::text`] with its own line height.
    pub fn text_line(
        &self,
        s: impl Into<String>,
        face: Face,
        weight: u16,
        size: f32,
        color: Color,
        em: f32,
        line: LineHeight,
    ) -> impl Bundle {
        (Text::new(s), self.font(face, weight, size), TextColor(color), LetterSpacing::Px(size * em), line)
    }

    /// `.lbl`: Barlow Condensed 600, 13 px, 0.14 em, upper case, `--text-mid`.
    pub fn lbl(&self, s: impl Into<String>) -> impl Bundle {
        self.role(TextRole::Lbl, s)
    }

    /// `.micro`: Barlow Condensed 600, 11 px, 0.16 em, upper case, `--text-low`.
    pub fn micro(&self, s: impl Into<String>) -> impl Bundle {
        self.role(TextRole::Micro, s)
    }

    /// The `TextFont` of a role (with tabular figures where the role uses them).
    pub fn role_font(&self, role: TextRole) -> TextFont {
        let r = role.spec();
        let handle = if r.italic { self.body_italic.clone() } else { self.handle(r.face, r.weight) };
        let mut f = TextFont::from_font_size(r.size).with_font(handle);
        if r.tnum {
            f.font_features = [FontFeatureTag::TABULAR_FIGURES].into();
        }
        f
    }

    /// A text entity in a role, in the role's colour.
    pub fn role(&self, role: TextRole, s: impl Into<String>) -> impl Bundle {
        self.role_color(role, s, role.spec().color)
    }

    /// A text entity in a role, in another colour.
    pub fn role_color(&self, role: TextRole, s: impl Into<String>, color: Color) -> impl Bundle {
        let r = role.spec();
        (Text::new(role.case(s)), self.role_font(role), TextColor(color), LetterSpacing::Px(r.size * r.em), r.line)
    }
}

// --- Dark ink on light fills
// Bevy blends glyph edges in linear light while the browser blends them in sRGB, so dark text on a light
// fill (BG0 on TEXT_HI: primary buttons, a selected segment, chip or keycap) loses weight: its edge pixels
// come out far lighter (measured: JOIN LOBBY 12 and a selected JOIN CODE segment 15 levels lighter on average
// than the mockups). Light text on dark is not affected. The kit gives every dark text a copy of itself
// [`INK_WEIGHT_PX`] to the right (a `TextShadow` in its own colour), which brings the weight back. It follows
// the text colour, so ink that turns dark only when a segment is selected gets it then, and loses it again.

/// How far the thickening copy of dark ink sits to the right (logical px).
pub const INK_WEIGHT_PX: f32 = 0.5;

/// The `TextShadow` the kit added to thicken dark ink (one a screen set itself is left alone).
#[derive(Component, Debug, Clone, Copy)]
pub struct InkWeight;

/// A text colour that is dark enough to need [`INK_WEIGHT_PX`]: dark ink, mostly opaque.
pub fn is_dark_ink(c: Color) -> bool {
    let s = c.to_srgba();
    s.alpha > 0.5 && 0.2126 * s.red + 0.7152 * s.green + 0.0722 * s.blue < 0.25
}

pub(super) fn thicken_dark_ink(
    texts: Query<(Entity, &TextColor, Option<&TextShadow>, Has<InkWeight>), (With<Text>, Changed<TextColor>)>,
    mut commands: Commands,
) {
    for (e, color, shadow, ours) in &texts {
        if is_dark_ink(color.0) {
            if shadow.is_some() && !ours {
                continue;
            }
            let want = TextShadow { offset: Vec2::new(INK_WEIGHT_PX, 0.0), color: color.0 };
            if shadow.is_none_or(|s| s.offset != want.offset || s.color != want.color) {
                commands.entity(e).insert((want, InkWeight));
            }
        } else if ours {
            commands.entity(e).remove::<(TextShadow, InkWeight)>();
        }
    }
}

/// A row of the type scale.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RoleSpec {
    pub face: Face,
    pub weight: u16,
    pub size: f32,
    /// Letter spacing in em.
    pub em: f32,
    pub line: LineHeight,
    pub upper: bool,
    pub color: Color,
    pub tnum: bool,
    pub italic: bool,
}

/// Every text role of the hub screens (the spec's type scale). Use these instead of hand-typed sizes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TextRole {
    // display
    Wordmark,
    DeathName,
    Downed,
    AgentXl,
    ScoreXl,
    NavXl,
    ScreenTitle,
    NavL,
    AgentL,
    SbTitle,
    NavQuit,
    ModalTitle,
    FlyoutTitle,
    CodeXl,
    TeamName,
    MapName,
    RespawnTitle,
    ValueL,
    NavM,
    NavSub,
    PlayerName,
    CodeM,
    InputBig,
    TabWeapon,
    LobbyName,
    // headings
    H2,
    H2Card,
    H2Small,
    // controls
    BtnL,
    Btn,
    Apply,
    BtnS,
    BtnXs,
    RailTab,
    InputM,
    Stepper,
    RowName,
    Field,
    TierBox,
    ListName,
    SlotValue,
    Tab,
    Chip,
    Select,
    AbilityTitle,
    Seg,
    Toggle,
    CoreName,
    Wclass,
    MenuItem,
    KeybindCap,
    Keycap,
    TierText,
    HotspotValue,
    StatusWord,
    GroupRow,
    Tag,
    TagXs,
    // labels
    RoleLine,
    StatusLine,
    NumCell,
    EmptySlot,
    Hint,
    RowLabel,
    Unit,
    Lbl,
    NavSmall,
    Subtitle,
    StatKey,
    TableHead,
    TabSub,
    Micro,
    // condensed 500
    Num,
    Tick,
    CoreDesc,
    // body
    BodyL,
    ModalBody,
    KvValue,
    Chat,
    ChatSystem,
    TableCell,
    Body,
    Help,
    CardLine,
    Note,
    NoteBold,
    Desc,
    Sub,
}

/// The browser's `line-height: normal` for Barlow and Barlow Condensed (ascent 1.0 em, descent 0.2 em): Chrome
/// rounds the ascent and the descent to whole pixels, so 11 px text gets a 13 px line box, 13 px a 16, 16 px
/// a 19 and 44 px a 53. Bevy's `RelativeToFont(1.2)` gave 13.2 / 15.6 / 19.2 / 52.8, which the layout rounded
/// into 1-2 px drifts against the mockups (a tab row 1 px tall, the version lines 2 px high).
pub const fn css_normal_line(size: f32) -> f32 {
    const fn round(v: f32) -> f32 {
        (v + 0.5) as i32 as f32
    }
    round(size) + round(size * 0.2)
}

const fn d(weight: u16, size: f32, em: f32, upper: bool, color: Color) -> RoleSpec {
    RoleSpec {
        face: Face::Display,
        weight,
        size,
        em,
        line: LineHeight::Px(css_normal_line(size)),
        upper,
        color,
        tnum: false,
        italic: false,
    }
}

const fn b(weight: u16, size: f32, color: Color) -> RoleSpec {
    RoleSpec {
        face: Face::Body,
        weight,
        size,
        em: 0.0,
        line: LineHeight::Px(css_normal_line(size)),
        upper: false,
        color,
        tnum: false,
        italic: false,
    }
}

impl RoleSpec {
    const fn lh(mut self, px: f32) -> Self {
        self.line = LineHeight::Px(px);
        self
    }
    const fn lh_rel(mut self, k: f32) -> Self {
        self.line = LineHeight::RelativeToFont(k);
        self
    }
    const fn tnum(mut self) -> Self {
        self.tnum = true;
        self
    }
    const fn italic(mut self) -> Self {
        self.italic = true;
        self
    }
}

impl TextRole {
    pub const fn spec(self) -> RoleSpec {
        use TextRole::*;
        match self {
            Wordmark => d(700, 84.0, 0.14, true, TEXT_HI).lh(80.0),
            DeathName => d(700, 72.0, 0.08, true, TEXT_HI).lh(72.0),
            Downed => d(700, 64.0, 0.16, true, FLESH_TEXT).lh(64.0),
            AgentXl => d(700, 56.0, 0.16, true, TEXT_HI).lh(56.0),
            ScoreXl => d(700, 56.0, 0.0, false, TEXT_HI).lh(56.0).tnum(),
            NavXl => d(700, 44.0, 0.10, true, TEXT_MID),
            ScreenTitle => d(700, 40.0, 0.14, true, TEXT_HI),
            NavL => d(700, 36.0, 0.10, true, TEXT_MID),
            AgentL => d(700, 34.0, 0.12, true, TEXT_HI).lh(34.0),
            SbTitle => d(700, 34.0, 0.08, true, TEXT_HI),
            NavQuit => d(700, 32.0, 0.10, true, TEXT_LOW),
            ModalTitle => d(700, 32.0, 0.10, true, TEXT_HI),
            FlyoutTitle => d(700, 30.0, 0.12, true, TEXT_HI),
            CodeXl => d(700, 30.0, 0.24, true, TEXT_HI).tnum(),
            TeamName => d(700, 28.0, 0.14, true, TEXT_HI),
            MapName => d(700, 28.0, 0.14, true, TEXT_HI).lh(28.0),
            RespawnTitle => d(700, 28.0, 0.14, true, TEXT_HI),
            ValueL => d(700, 26.0, 0.0, false, TEXT_HI).lh(28.0).tnum(),
            NavM => d(700, 24.0, 0.10, true, TEXT_MID),
            NavSub => d(700, 24.0, 0.14, true, TEXT_MID),
            PlayerName => d(700, 24.0, 0.08, true, TEXT_HI),
            CodeM => d(700, 24.0, 0.20, true, TEXT_HI).tnum(),
            InputBig => d(700, 24.0, 0.0, false, TEXT_HI),
            TabWeapon => d(700, 22.0, 0.08, true, TEXT_MID),
            LobbyName => d(700, 22.0, 0.08, true, TEXT),
            H2 => d(700, 20.0, 0.18, true, TEXT_HI),
            H2Card => d(700, 18.0, 0.18, true, TEXT_HI),
            H2Small => d(700, 17.0, 0.18, true, TEXT_HI),
            BtnL => d(700, 20.0, 0.12, true, TEXT_HI),
            Btn => d(700, 18.0, 0.12, true, TEXT_HI),
            Apply => d(700, 15.0, 0.12, true, BG0),
            BtnS => d(700, 14.0, 0.12, true, TEXT_HI),
            BtnXs => d(700, 13.0, 0.12, true, TEXT_HI),
            RailTab => d(700, 20.0, 0.14, true, TEXT_MID),
            InputM => d(700, 20.0, 0.06, false, TEXT_HI),
            Stepper => d(700, 20.0, 0.0, false, TEXT_HI).tnum(),
            RowName => d(700, 20.0, 0.06, true, TEXT_HI),
            Field => d(700, 18.0, 0.0, false, TEXT_HI).tnum(),
            TierBox => d(700, 18.0, 0.10, true, TEXT_HI),
            ListName => d(700, 17.0, 0.06, false, TEXT_HI),
            SlotValue => d(700, 17.0, 0.04, true, TEXT_HI).lh(18.0),
            Tab => d(700, 16.0, 0.16, true, TEXT_MID),
            Chip => d(700, 16.0, 0.14, true, TEXT_MID),
            Select => d(700, 16.0, 0.06, false, TEXT_HI),
            AbilityTitle => d(700, 16.0, 0.10, true, TEXT_HI),
            Seg => d(700, 15.0, 0.08, false, TEXT_MID),
            Toggle => d(700, 15.0, 0.12, true, TEXT_MID),
            CoreName => d(700, 15.0, 0.14, true, TEXT_MID),
            Wclass => d(700, 15.0, 0.16, true, TEXT_LOW),
            MenuItem => d(700, 15.0, 0.12, true, TEXT),
            KeybindCap => d(700, 15.0, 0.04, true, TEXT_HI),
            Keycap => d(700, 13.0, 0.04, true, BG0),
            TierText => d(700, 13.0, 0.08, true, TEXT_HI),
            HotspotValue => d(700, 13.0, 0.12, true, TEXT_HI),
            StatusWord => d(700, 13.0, 0.10, true, ALLY),
            GroupRow => d(700, 13.0, 0.18, true, TEXT_MID),
            Tag => d(700, 11.0, 0.20, true, BG0),
            TagXs => d(700, 10.0, 0.16, true, BG0),
            RoleLine => d(600, 15.0, 0.22, true, TEAL),
            StatusLine => d(600, 15.0, 0.14, true, TEXT_MID),
            NumCell => d(600, 15.0, 0.0, false, TEXT_MID).tnum(),
            EmptySlot => d(600, 15.0, 0.16, true, TEXT_LOW),
            Hint => d(600, 14.0, 0.14, true, TEXT_MID),
            RowLabel => d(600, 14.0, 0.12, true, TEXT),
            Unit => d(600, 14.0, 0.08, false, TEXT_MID),
            Lbl => d(600, 13.0, 0.14, true, TEXT_MID),
            NavSmall => d(600, 13.0, 0.18, true, TEXT_LOW),
            Subtitle => d(600, 13.0, 0.20, true, TEXT_MID),
            StatKey => d(600, 12.5, 0.14, true, TEXT_MID),
            TableHead => d(600, 12.0, 0.16, true, TEXT_MID),
            TabSub => d(600, 12.0, 0.18, true, TEXT_LOW),
            Micro => d(600, 11.0, 0.16, true, TEXT_LOW),
            Num => d(500, 15.0, 0.0, false, TEXT_HI).tnum(),
            Tick => d(500, 11.0, 0.0, false, TEXT_LOW).tnum(),
            CoreDesc => d(500, 11.0, 0.06, true, TEXT_LOW).lh_rel(1.25),
            BodyL => b(400, 17.0, TEXT),
            ModalBody => b(400, 16.0, TEXT).lh(24.0),
            KvValue => b(400, 15.0, TEXT),
            Chat => b(400, 14.5, TEXT).lh(23.2),
            ChatSystem => b(400, 14.5, TEXT_MID).lh(23.2).italic(),
            TableCell => b(400, 14.5, TEXT),
            Body => b(400, 14.0, TEXT),
            Help => b(400, 13.0, TEXT_MID).lh(18.85),
            CardLine => b(400, 13.0, TEXT_MID),
            Note => b(400, 12.5, TEXT_MID).lh_rel(1.45),
            NoteBold => b(700, 12.5, TEXT_HI).lh_rel(1.45),
            Desc => b(400, 12.5, TEXT_MID).lh_rel(1.35),
            Sub => b(400, 12.0, TEXT_MID),
        }
    }

    /// The copy as this role shows it (upper-cased for upper-case roles).
    pub fn case(self, s: impl Into<String>) -> String {
        let s = s.into();
        if self.spec().upper { s.to_uppercase() } else { s }
    }

    /// Letter spacing in px.
    pub fn spacing_px(self) -> f32 {
        let r = self.spec();
        r.size * r.em
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn em_spacing_converts_to_px() {
        assert!((TextRole::Wordmark.spacing_px() - 11.76).abs() < 1e-4);
        assert!((TextRole::Lbl.spacing_px() - 1.82).abs() < 1e-4);
        assert!((TextRole::NavXl.spacing_px() - 4.4).abs() < 1e-4);
    }

    /// The browser's normal line box for Barlow: whole-pixel ascent (1 em) plus whole-pixel descent (.2 em).
    #[test]
    fn normal_line_height_matches_the_browser() {
        assert_eq!(css_normal_line(11.0), 13.0, "micro: the version lines are 13 tall");
        assert_eq!(css_normal_line(13.0), 16.0, ".lbl rows are 16 tall");
        assert_eq!(css_normal_line(16.0), 19.0, "a tab box is 10 + 19 + 10");
        assert_eq!(css_normal_line(24.0), 29.0, "the player card's name line");
        assert_eq!(css_normal_line(30.0), 36.0, "a flyout title");
        assert_eq!(css_normal_line(44.0), 53.0);
        assert_eq!(TextRole::Tab.spec().line, LineHeight::Px(19.0));
    }

    #[test]
    fn upper_case_roles_upper_case_their_copy() {
        assert_eq!(TextRole::NavXl.case("Gun range"), "GUN RANGE");
        assert_eq!(TextRole::Unit.case("cm / 360°"), "cm / 360°");
        assert!(TextRole::ChatSystem.spec().italic);
        assert!(TextRole::Field.spec().tnum);
    }
}
