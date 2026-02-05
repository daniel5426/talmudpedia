import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

type DataPointsProps = {
  scrollOffset?: number;
};

export default function DataPoints({ scrollOffset = 0 }: DataPointsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const pointsRef = useRef<THREE.Mesh[]>([]);
  const raycasterRef = useRef(new THREE.Raycaster());
  const mouseRef = useRef(new THREE.Vector2());
  const [hoveredLabel, setHoveredLabel] = useState<string | null>(null);
  const [labelPosition, setLabelPosition] = useState({ x: 0, y: 0 });
  const [isMobile, setIsMobile] = useState(false);
  const isHoveringRef = useRef(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const dataPoints = [
    "תורה", "נביאים", "כתובים", "תלמוד", "משנה",
    "גמרא", "מדרש", "זוהר", "רש\"י", "רמב\"ם",
    "שולחן ערוך", "משנה תורה", "ספר יצירה", "תוספות", "רי\"ף",
    "רמב\"ן", "אור החיים", "ספר החינוך", "מסכת ברכות", "מסכת שבת",
    "מסכת פסחים", "מסכת יומא", "מסכת סוכה", "מסכת ראש השנה", "מסכת מגילה",
    "מסכת תענית", "מסכת מועד קטן", "מסכת חגיגה", "מסכת יבמות", "מסכת כתובות",
    "מסכת נדרים", "מסכת נזיר", "מסכת סוטה", "מסכת גיטין", "מסכת קידושין",
    "מסכת בבא קמא", "מסכת בבא מציעא", "מסכת בבא בתרא", "מסכת סנהדרין", "מסכת מכות",
    "מסכת שבועות", "מסכת עבודה זרה", "מסכת הוריות", "מסכת זבחים", "מסכת מנחות",
    "מסכת חולין", "מסכת בכורות", "מסכת ערכין", "מסכת תמורה", "מסכת כריתות",
    "מסכת מעילה", "מסכת תמיד", "מסכת נידה", "בראשית", "שמות",
    "ויקרא", "במדבר", "דברים", "יהושע", "שופטים",
    "שמואל", "מלכים", "ישעיהו", "ירמיהו", "יחזקאל",
    "תרי עשר", "תהילים", "משלי", "איוב", "שיר השירים",
    "רות", "איכה", "קהלת", "אסתר", "דניאל",
    "עזרא", "נחמיה", "דברי הימים"
  ];

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;

    // Scene setup
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const isMobile = window.innerWidth < 768;
    
    const camera = new THREE.PerspectiveCamera(
      75,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    camera.position.z = isMobile ? 18 : 12;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true
    });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Create the central point
    const centerGeometry = new THREE.SphereGeometry(0.12, 16, 16);
    const centerMaterial = new THREE.MeshStandardMaterial({ 
      color: 0xffffff,
      emissive: 0xffffff,
      emissiveIntensity: 2
    });
    const centerPoint = new THREE.Mesh(centerGeometry, centerMaterial);
    scene.add(centerPoint);
    
    const pointLight = new THREE.PointLight(0xffffff, 2, 20);
    pointLight.position.set(0, 0, 0);
    scene.add(pointLight);

    // Create particle system
    const group = new THREE.Group();
    const particles: THREE.Mesh[] = [];
    const lines: THREE.Line[] = [];

    dataPoints.forEach((label, i) => {
      // Random spherical distribution
      const phi = Math.acos(-1 + (2 * i) / dataPoints.length);
      const theta = Math.sqrt(dataPoints.length * Math.PI) * phi;
      
      const distance = 5 + Math.random() * 2.5;
      const x = distance * Math.cos(theta) * Math.sin(phi);
      const y = distance * Math.sin(theta) * Math.sin(phi);
      const z = distance * Math.cos(phi);

      // Create particle (small cube)
      const particleGeometry = new THREE.BoxGeometry(0.12, 0.12, 0.12);
      const particleMaterial = new THREE.MeshBasicMaterial({
        color: 0x001A3C,
        transparent: true,
        opacity: 0.8
      });
      const particle = new THREE.Mesh(particleGeometry, particleMaterial);
      particle.position.set(x, y, z);
      particle.userData = { label, originalColor: 0x001A3C };
      particles.push(particle);
      group.add(particle);

      // Create line from center to particle
      const lineGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(x, y, z)
      ]);
      const lineMaterial = new THREE.LineBasicMaterial({ 
        color: 0x555555,
        transparent: true,
        opacity: 0.7
      });
      const line = new THREE.Line(lineGeometry, lineMaterial);
      lines.push(line);
      group.add(line);
    });

    pointsRef.current = particles;
    scene.add(group);

    // Mouse move handler
    const handleMouseMove = (event: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouseRef.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouseRef.current.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      // Raycasting
      raycasterRef.current.setFromCamera(mouseRef.current, camera);
      const intersects = raycasterRef.current.intersectObjects(particles);

      // Reset all particles
      particles.forEach(p => {
        (p.material as THREE.MeshBasicMaterial).color.setHex(p.userData.originalColor);
        p.scale.set(1, 1, 1);
      });

      if (intersects.length > 0) {
        const intersected = intersects[0].object as THREE.Mesh;
        (intersected.material as THREE.MeshBasicMaterial).color.setHex(0xffffff);
        intersected.scale.set(1.5, 1.5, 1.5);

        isHoveringRef.current = true;
        setHoveredLabel(intersected.userData.label);
        setLabelPosition({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top
        });
      } else {
        isHoveringRef.current = false;
        setHoveredLabel(null);
      }
    };

    container.addEventListener('mousemove', handleMouseMove);

    // Animation loop
    let animationId: number;
    const animate = () => {
      animationId = requestAnimationFrame(animate);

      // Slow rotation on Y axis - stop when hovering
      if (!isHoveringRef.current) {
        group.rotation.y += 0.001;
      }

      renderer.render(scene, camera);
    };
    animate();

    // Handle resize
    const handleResize = () => {
      if (!container) return;
      const width = container.clientWidth;
      const height = container.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      container.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationId);
      renderer.dispose();
      if (renderer.domElement && renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative w-full h-full bg-transparent overflow-hidden">
      <div ref={containerRef} className="absolute inset-0 z-10" />
      
      <div className="pointer-events-none absolute inset-0 flex flex-col justify-center items-center z-50">
        <div 
          className="text-3xl md:text-6xl lg:text-8xl tracking-wider mb-4 transition-transform duration-75 ease-out"
          style={{ 
            transform: `translateX(${scrollOffset * (isMobile ? 0.2 : 0.3)}px)`,
            fontFamily: 'Shmulik, serif',
            color: '#ffffff',
            opacity: 1
          }}
        >
          תחקור ותעיין
        </div>
        <div 
          className="text-3xl md:text-6xl lg:text-8xl tracking-wider transition-transform duration-75 ease-out"
          style={{ 
            transform: `translateX(${-scrollOffset * (isMobile ? 0.2 : 0.3)}px)`,
            fontFamily: 'Shmulik, serif',
            color: '#ffffff',
            opacity: 1
          }}
        >
          בכל התורה 
        </div>
      </div>
      
      {hoveredLabel && (
        <div
          className="absolute pointer-events-none bg-white text-black px-3 py-1.5 rounded text-sm font-medium shadow-lg z-100"
          dir="rtl"
          style={{
            left: `${labelPosition.x}px`,
            top: `${labelPosition.y - 40}px`,
            transform: 'translateX(-50%)'
          }}
        >
          {hoveredLabel}
        </div>
      )}
    </div>
  );
}