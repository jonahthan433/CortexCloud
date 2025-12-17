import { Bot, MessageSquare, Zap, Globe, BookOpen, Pencil, Palette, Mic, Download, Cloud } from 'lucide-react';
import FadeIn from './FadeIn';

const HowItWorksSection = () => {
  const steps = [
    {
      number: '01',
      title: 'AI Agents that can do anything',
      description: 'Handles bookings, refunds, customer support and more.',
      icon: Bot,
      highlights: [
        { icon: Globe, text: 'Natural language input, no special commands.' },
        { icon: BookOpen, text: 'Smart prompt suggestions to guide you.' },
      ],
    },
    {
      number: '02',
      title: 'Instant, Human-like responses',
      description: 'These AI Agents instantly processes requests and delivers accurate, natural-sounding responses tailored to your clients needs.',
      icon: MessageSquare,
      highlights: [
        { icon: Pencil, text: 'Real-Time responses' },
        { icon: Palette, text: 'Multiple tones: professional, casual, witty, etc.' },
        { icon: Mic, text: 'Optional voice or markdown output.' },
      ],
    },
    {
      number: '03',
      title: 'Take action or refine further',
      description: 'Your AI agent does more than respond. It understands. It schedules. It adapts.',
      icon: Zap,
      highlights: [
        { icon: Download, text: 'Trained just for you' },
        { icon: Cloud, text: 'Auto-save + history to revisit anytime.' },
      ],
    },
  ];

  return (
    <section className="py-16 md:py-32 relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-secondary/20" />
      <div className="absolute top-1/2 left-0 w-64 md:w-96 h-64 md:h-96 bg-primary/5 rounded-full blur-3xl" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <FadeIn>
          <div className="text-center mb-12 md:mb-24">
            <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
              How it works
            </span>
            <h2 className="text-mobile-title lg:text-5xl font-bold font-display">
              How The AI Agent works in{' '}
              <span className="text-gradient">3 simple steps</span>, 24/7.
            </h2>
          </div>
        </FadeIn>

        {/* Steps */}
        <div className="space-y-16 md:space-y-32">
          {steps.map((step, index) => (
            <div
              key={index}
              className={`grid lg:grid-cols-2 gap-8 md:gap-12 items-center ${
                index % 2 === 1 ? 'lg:flex-row-reverse' : ''
              }`}
            >
              {/* Content */}
              <FadeIn direction={index % 2 === 0 ? 'left' : 'right'}>
                <div className={`space-y-4 md:space-y-6 ${index % 2 === 1 ? 'lg:order-2' : ''}`}>
                  <div className="inline-flex items-center justify-center w-14 h-14 md:w-16 md:h-16 rounded-2xl bg-gradient-primary text-2xl md:text-3xl font-bold font-display">
                    {step.number}
                  </div>
                  <h3 className="text-xl sm:text-2xl lg:text-4xl font-bold font-display">
                    {step.title}
                  </h3>
                  <p className="text-muted-foreground text-mobile-body">
                    {step.description}
                  </p>
                  <div className="space-y-3 md:space-y-4 pt-2 md:pt-4">
                    {step.highlights.map((highlight, hIndex) => (
                      <div key={hIndex} className="flex items-center gap-3 md:gap-4">
                        <div className="w-10 h-10 rounded-xl glass flex items-center justify-center flex-shrink-0">
                          <highlight.icon size={18} className="text-primary md:w-5 md:h-5" />
                        </div>
                        <span className="text-foreground text-sm md:text-base">{highlight.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </FadeIn>

              {/* Visual */}
              <FadeIn direction={index % 2 === 0 ? 'right' : 'left'} delay={0.1}>
                <div className={`relative ${index % 2 === 1 ? 'lg:order-1' : ''}`}>
                  <div className="absolute -inset-4 bg-gradient-to-r from-primary/10 to-accent/10 rounded-3xl blur-2xl" />
                  <div className="relative glass-strong rounded-2xl p-6 md:p-8 min-h-[200px] md:min-h-[300px] flex items-center justify-center">
                    <step.icon size={60} className="text-primary animate-float md:w-20 md:h-20" />
                  </div>
                </div>
              </FadeIn>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
