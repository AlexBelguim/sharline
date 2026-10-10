"""Generate deterministic simulation step brushes from the exported geometry handoff."""
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'game/crates/vetf_sim/src/maps/showhome_steps.rs'


def main():
    data=json.loads((HERE/'kit/ground_steps.json').read_text())
    rows=[r for r in data['runs']if r['collision_required']]
    lines=['//! Generated from assets/maps/showhome/kit/ground_steps.json. Rebuild with sync_ground_steps.py.',
           'use crate::movement::collision::{Brush, BrushKind, CollisionWorld, Look, Plane};',
           'use glam::Vec3;',
           'struct Step { footprint: &\'static [[f32; 2]], height: f32 }',
           'const STEPS: &[Step] = &[']
    for r in rows:
        points=r['footprint']
        poly=', '.join('['+f'{p[0]:.5f}, {p[1]:.5f}'+']'for p in points)
        lines.append(f'    Step {{ footprint: &[{poly}], height: {r["height_m"]:.5f} }}, // {r["id"]}')
    lines+=[''' ];

pub(super) fn add(world: &mut CollisionWorld) {
    for step in STEPS {
        let mut min = Vec3::splat(f32::MAX);
        let mut max = Vec3::splat(f32::MIN);
        let mut centre = Vec3::ZERO;
        for &[x, north] in step.footprint {
            let p = Vec3::new(x, 0.0, -north);
            min = min.min(p); max = max.max(p); centre += p;
        }
        centre /= step.footprint.len() as f32;
        max.y = step.height;
        let mut planes = vec![Plane { normal: Vec3::Y, dist: step.height },
                              Plane { normal: Vec3::NEG_Y, dist: 0.0 }];
        for i in 0..step.footprint.len() {
            let [x0, y0] = step.footprint[i];
            let [x1, y1] = step.footprint[(i+1)%step.footprint.len()];
            let p = Vec3::new(x0, 0.0, -y0);
            let edge = Vec3::new(x1-x0, 0.0, y0-y1);
            let mut normal = Vec3::new(edge.z, 0.0, -edge.x).normalize();
            if normal.dot(centre-p) > 0.0 { normal = -normal; }
            planes.push(Plane { normal, dist: normal.dot(p) });
        }
        world.brushes.push(Brush { planes, min, max, kind: BrushKind::Solid,
                                  look: Look::Invisible, ramp: None });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn registered_steps_are_short_solid_convex_brushes() {
        let mut world = CollisionWorld::default();
        add(&mut world);
        assert_eq!(world.brushes.len(), 344);
        for brush in world.brushes {
            assert!(brush.max.y > 0.02 && brush.max.y <= 0.12);
            assert!(brush.min.x >= -0.05 && brush.max.x <= 72.05);
            assert!(brush.min.z >= -48.05 && brush.max.z <= 0.05);
            let centre = (brush.min + brush.max) * 0.5;
            assert!(brush.planes.iter().all(|p| p.normal.dot(centre) <= p.dist+0.01));
        }
    }
}
''']
    OUT.write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('GENERATED',len(rows),'solid ground step brushes',OUT)


if __name__=='__main__':main()
