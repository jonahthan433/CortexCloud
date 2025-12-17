import { Settings, Layers, Workflow } from 'lucide-react';
import FadeIn from './FadeIn';

const CustomSolutionsSection = () => {
  const solutions = [
    {
      icon: Settings,
      title: 'Optimisation',
      description: 'We optimize workflows by connecting systems, automating tasks, and minimizing wasted time.',
    },
    {
      icon: Layers,
      title: 'Custom Projects',
      description: 'We analyze your workflows and implement AI solutions to streamline and optimize them.',
    },
    {
      icon: Workflow,
      title: 'Automation',
      description: 'We automate daily tasks like customer support and emails, saving you valuable hours.',
    },
  ];

  return (
    <section className="py-16 md:py-32 relative">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <FadeIn>
          <div className="text-center mb-8 md:mb-16">
            <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
              Custom Solutions
            </span>
            <h2 className="text-mobile-title lg:text-5xl font-bold font-display">
              Create Your Custom <span className="text-gradient">AI Employee</span>
            </h2>
          </div>
        </FadeIn>

        {/* Solutions Grid */}
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4 md:gap-8">
          {solutions.map((solution, index) => (
            <FadeIn key={index} delay={index * 0.1}>
              <div className="group relative h-full">
                <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-0 group-hover:opacity-20 blur-xl transition-opacity duration-500" />
                <div className="relative glass-strong rounded-2xl p-6 md:p-8 h-full transition-transform duration-300 hover:-translate-y-2 touch-manipulation active:scale-[0.98]">
                  <div className="w-12 h-12 md:w-14 md:h-14 rounded-xl bg-gradient-primary flex items-center justify-center mb-4 md:mb-6">
                    <solution.icon size={24} className="text-primary-foreground md:w-7 md:h-7" />
                  </div>
                  <h3 className="text-lg md:text-xl font-bold font-display mb-3 md:mb-4">
                    {solution.title}
                  </h3>
                  <p className="text-sm md:text-base text-muted-foreground">
                    {solution.description}
                  </p>
                </div>
              </div>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  );
};

export default CustomSolutionsSection;
